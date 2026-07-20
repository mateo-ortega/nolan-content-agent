"""
nolan-research — ciclo de investigacion de senales para Sapiens by Shift.

Uso:
    python research.py [--nichos padres,jovenes_preicfes] [--trigger cron|telegram|manual] [--dry-run]
    python research.py --dry-run  # sin LLM, solo recoleccion y log

Salida:
    JSON shortlist a stdout (capturado por Nolan para produccion)
    memory/trends.sqlite actualizado
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import httpx
import yaml

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent
))
sys.path.insert(0, str(PROJECT_ROOT))

from sapiens.nolan_llm_router import load_router   # noqa: E402
from sapiens._paths import pieces_db_path           # noqa: E402

SOURCES_CFG      = PROJECT_ROOT / "config" / "sources.yaml"
SCHEMA_SQL       = PROJECT_ROOT / "memory" / "schemas" / "trends.sql"
DB_PATH          = PROJECT_ROOT / "memory" / "trends.sqlite"
LOG_PATH         = PROJECT_ROOT / "logs" / "research.log"
EVERGREEN_PATH   = PROJECT_ROOT / "prompts" / "evergreen_topics.yaml"
PIECES_DB_PATH   = pieces_db_path()

ALL_NICHOS = ["jovenes_preicfes", "padres", "universitarios", "adultos_ia", "pymes"]

_CLASSIFY_SYSTEM = """Eres el analizador de senales de contenido de Nolan, agente de @sapiens.ed (Sapiens by Shift, Colombia).

Nichos objetivo:
- jovenes_preicfes: estudiantes colombianos 15-18 anos preparando ICFES / admision universitaria
- padres: padres de hijos en edad escolar (6-18), clase media/media-alta, Colombia
- adultos_ia: profesionales 25-45 aprendiendo IA para productividad y trabajo
- pymes: duenos de pymes colombianas

Valores SOUL (prohibiciones duras):
- Nunca prometer resultados garantizados
- Nunca FOMO/miedo al reemplazo por IA
- Nunca atajos magicos o dinero facil
- Nunca afirmaciones sin fuente en temas tecnicos

Tu tarea: dado un batch de senales (RSS, noticias, tendencias), producir un shortlist editorial.

RESPONDE SOLO CON JSON VALIDO (sin markdown, sin explicacion fuera del JSON):
{
  "shortlist": [
    {
      "tema": "titulo breve del tema (max 10 palabras)",
      "nicho": "jovenes_preicfes|padres|adultos_ia|pymes",
      "angulo": "angulo editorial especifico para Sapiens (1 frase)",
      "score": 0.0,
      "formato_sugerido": "carrusel|animacion",
      "ethics_risk": "low|medium|high",
      "fuentes": [{"url": "...", "titulo": "..."}],
      "signal_indices": [0, 1]
    }
  ]
}

Reglas:
- Max 3 temas por nicho. Prioriza: recencia (<72h = +0.2), calidad de fuentes, encaje con SOUL.
- score: 0.0-1.0 donde 0.9+ = urgente, 0.7-0.89 = muy relevante, <0.5 = descartar.
- Si una senal no encaja en ningun nicho, ignorarla.
- Prefiere carrusel por defecto; animacion solo si el contenido es visual/demostrativo.
"""


def main():
    ap = argparse.ArgumentParser(description="Ciclo de investigacion de senales")
    ap.add_argument("--nichos", default=",".join(ALL_NICHOS),
                    help="Nichos separados por coma")
    ap.add_argument("--trigger", default="manual",
                    choices=["cron", "telegram", "manual"])
    ap.add_argument("--dry-run", action="store_true",
                    help="Sin LLM ni escritura a DB; solo recoleccion y log")
    args = ap.parse_args()

    nichos = [n.strip() for n in args.nichos.split(",") if n.strip()]
    ciclo_ts = datetime.now(tz=timezone.utc).isoformat()

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _log(f"[research] ciclo={ciclo_ts}  trigger={args.trigger}  nichos={nichos}  dry_run={args.dry_run}")
    _startup_health_check()

    # 1. Cargar config
    with open(SOURCES_CFG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 2. Init DB
    db = _init_db()

    # 3. Recolectar senales
    raw: list[dict] = []
    raw.extend(_collect_rss(cfg))
    raw.extend(_collect_google_trends(cfg))
    raw.extend(_collect_web_search(cfg))   # Tavily > Perplexity > DuckDuckGo
    raw.extend(_collect_apify(cfg))        # stub si falta APIFY_TOKEN

    _log(f"[research] senales crudas={len(raw)}")

    # 4. Deduplicar contra DB
    new_signals = _dedupe(raw, db)
    _log(f"[research] nuevas tras dedupe={len(new_signals)}")

    # 5. LLM: clasificar + clusterizar + puntuar
    shortlist = []
    llm_cost = 0.0
    if new_signals and not args.dry_run:
        shortlist, llm_cost = _llm_process(new_signals, nichos)
    elif not new_signals:
        _log("[research] sin senales nuevas, cargando shortlist existente de DB")
        shortlist = _load_existing_shortlist(db, nichos)
    else:
        _log("[research] dry-run: omitiendo LLM")

    # 5b. Floor evergreen: si el shortlist tiene < 3 temas, completar con evergreen
    if len(shortlist) < 3:
        evergreen_added = _fill_from_evergreen(shortlist, nichos)
        if evergreen_added:
            _log(f"[research] floor evergreen: +{len(evergreen_added)} temas añadidos")
            shortlist.extend(evergreen_added)

    # 6. Escribir a DB
    if not args.dry_run:
        _write_signals(db, new_signals, ciclo_ts)
        _write_clusters(db, shortlist, ciclo_ts)
        _write_cycle(db, ciclo_ts, args.trigger, nichos, raw, new_signals, shortlist, llm_cost)
        _check_research_degraded(db)

    # 7. Salida
    result = {
        "ciclo_ts": ciclo_ts,
        "signals_ingested": len(new_signals),
        "shortlist": shortlist,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _log(f"[research] OK  shortlist={len(shortlist)}  llm_cost=${llm_cost:.4f}")


# ---------------------------------------------------------------------------
# Recoleccion de senales
# ---------------------------------------------------------------------------

def _collect_rss(cfg: dict) -> list[dict]:
    feeds = cfg.get("rss", {}).get("feeds", [])
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
    signals = []
    for feed in feeds:
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries[:12]:
                pub = _parse_date(entry.get("published", "") or entry.get("updated", ""))
                if pub and pub < cutoff:
                    continue
                title = entry.get("title", "").strip()
                link  = entry.get("link", "").strip()
                if not title or not link:
                    continue
                signals.append({
                    "source_type": "rss",
                    "source":      feed["name"],
                    "title":       title,
                    "url":         link,
                    "summary":     _strip_html(entry.get("summary", ""))[:300],
                    "published":   pub.isoformat() if pub else "",
                    "tags":        json.dumps(feed.get("tags", [])),
                })
        except Exception as e:
            _log(f"[research] WARN RSS {feed['name']}: {e}")
    _log(f"[research] RSS: {len(signals)} entradas")
    return signals


def _collect_google_trends(cfg: dict) -> list[dict]:
    try:
        # Patch de compatibilidad pytrends 4.9.x con urllib3 2.x
        # (method_whitelist -> allowed_methods en urllib3 2.0)
        import urllib3.util.retry as _r
        if not hasattr(_r.Retry.__init__, "_patched_nolan"):
            _orig = _r.Retry.__init__
            def _init_patch(self, *a, **kw):
                if "method_whitelist" in kw:
                    kw["allowed_methods"] = kw.pop("method_whitelist")
                _orig(self, *a, **kw)
            _init_patch._patched_nolan = True
            _r.Retry.__init__ = _init_patch
        from pytrends.request import TrendReq  # type: ignore
    except ImportError:
        _log("[research] WARN: pytrends no instalado, saltando Google Trends")
        return []

    trends_cfg = cfg.get("google_trends", {})
    keywords = trends_cfg.get("tracked_keywords", [])
    geo = trends_cfg.get("geo", "CO")
    if not keywords:
        return []

    # Apify proxies requieren "Proxy external access" (plan pago). Google Trends
    # falla con 429 desde IPs de datacenter; se maneja de forma silenciosa abajo.
    signals = []
    try:
        pt = TrendReq(hl="es-CO", tz=-300, timeout=(10, 30), retries=2, backoff_factor=1)
        # Procesar en batches de 5 (limite de pytrends)
        for i in range(0, len(keywords), 5):
            batch = keywords[i:i+5]
            try:
                pt.build_payload(batch, geo=geo, timeframe="now 7-d")
                df = pt.interest_over_time()
                if df.empty:
                    continue
                for kw in batch:
                    if kw not in df.columns:
                        continue
                    avg_interest = int(df[kw].mean())
                    if avg_interest < 5:
                        continue
                    signals.append({
                        "source_type": "trends",
                        "source":      f"Google Trends CO",
                        "title":       kw,
                        "url":         f"https://trends.google.com/trends/explore?q={kw}&geo=CO",
                        "summary":     f"Interes promedio 7d: {avg_interest}/100 en Colombia",
                        "published":   datetime.now(tz=timezone.utc).isoformat(),
                        "tags":        json.dumps(["trends", geo]),
                    })
                time.sleep(2)  # evitar rate limit
            except Exception as e:
                _log(f"[research] WARN Trends batch {batch}: {e}")
    except Exception as e:
        _log(f"[research] WARN Google Trends: {e}")

    _log(f"[research] Google Trends: {len(signals)} keywords con interes")
    return signals


def _collect_web_search(cfg: dict) -> list[dict]:
    """
    Busqueda web para noticias recientes. Prioridad:
      1. Tavily (TAVILY_API_KEY) — diseñado para agentes LLM, devuelve contenido + URLs
      2. Perplexity (PERPLEXITY_API_KEY) — si disponible, alta calidad con citaciones
      3. DuckDuckGo — siempre disponible, sin clave, como fallback
    """
    queries = cfg.get("perplexity", {}).get("queries", [])
    max_q   = cfg.get("perplexity", {}).get("max_queries_per_cycle", 5)

    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    perp_key   = os.environ.get("PERPLEXITY_API_KEY", "")

    if tavily_key:
        signals = _search_tavily(queries[:max_q], tavily_key)
        _log(f"[research] Tavily: {len(signals)} resultados")
        return signals

    if perp_key:
        signals = _search_perplexity(queries[:max_q], perp_key)
        _log(f"[research] Perplexity: {len(signals)} citas")
        return signals

    # Fallback gratuito: DuckDuckGo
    signals = _search_duckduckgo(queries[:max_q])
    _log(f"[research] DuckDuckGo (fallback): {len(signals)} resultados")
    return signals


def _search_tavily(queries: list[str], api_key: str) -> list[dict]:
    signals = []
    for query in queries:
        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                headers={"Content-Type": "application/json"},
                json={
                    "api_key":        api_key,
                    "query":          query,
                    "search_depth":   "basic",
                    "topic":          "news",
                    "days":           7,
                    "max_results":    5,
                    "include_answer": False,
                },
                timeout=20,
            )
            resp.raise_for_status()
            for r in resp.json().get("results", []):
                signals.append({
                    "source_type": "news",
                    "source":      "tavily",
                    "query":       query,
                    "title":       r.get("title", query),
                    "url":         r.get("url", ""),
                    "summary":     (r.get("content") or r.get("snippet") or "")[:300],
                    "published":   r.get("published_date", datetime.now(tz=timezone.utc).isoformat()),
                    "low_conf":    0,
                    "tags":        json.dumps(["tavily", "news"]),
                })
            time.sleep(0.5)
        except Exception as e:
            _log(f"[research] WARN Tavily '{query}': {e}")
    return signals


def _search_perplexity(queries: list[str], api_key: str) -> list[dict]:
    signals = []
    for query in queries:
        try:
            resp = httpx.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": query}],
                    "max_tokens": 600,
                    "search_recency_filter": "week",
                    "return_citations": True,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data    = resp.json()
            cits    = data.get("citations", [])
            content = data["choices"][0]["message"]["content"]
            for cit in cits[:4]:
                signals.append({
                    "source_type": "news",
                    "source":      "perplexity",
                    "query":       query,
                    "title":       cit if isinstance(cit, str) else cit.get("title", query),
                    "url":         cit if isinstance(cit, str) else cit.get("url", ""),
                    "summary":     content[:300],
                    "published":   datetime.now(tz=timezone.utc).isoformat(),
                    "low_conf":    0 if cits else 1,
                    "tags":        json.dumps(["perplexity", "news"]),
                })
            time.sleep(1)
        except Exception as e:
            _log(f"[research] WARN Perplexity '{query}': {e}")
    return signals


def _search_duckduckgo(queries: list[str]) -> list[dict]:
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except ImportError:
        _log("[research] WARN: duckduckgo-search no instalado")
        return []

    signals = []
    with DDGS() as ddgs:
        for query in queries:
            try:
                results = list(ddgs.news(query, max_results=5, timelimit="w"))
                for r in results:
                    signals.append({
                        "source_type": "news",
                        "source":      "duckduckgo",
                        "query":       query,
                        "title":       r.get("title", query),
                        "url":         r.get("url", ""),
                        "summary":     r.get("body", "")[:300],
                        "published":   r.get("date", datetime.now(tz=timezone.utc).isoformat()),
                        "low_conf":    0,
                        "tags":        json.dumps(["duckduckgo", "news"]),
                    })
                time.sleep(1)
            except Exception as e:
                _log(f"[research] WARN DuckDuckGo '{query}': {e}")
    return signals


_APIFY_CADENCE_FILE = PROJECT_ROOT / "memory" / "apify_last_run.json"


def _apify_cadence_ok(cadence_hours: int) -> bool:
    """Devuelve True si han pasado al menos cadence_hours desde el último run de Apify."""
    if not _APIFY_CADENCE_FILE.exists():
        return True
    try:
        data = json.loads(_APIFY_CADENCE_FILE.read_text(encoding="utf-8"))
        last_ts = datetime.fromisoformat(data.get("last_run", "2000-01-01T00:00:00+00:00"))
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        elapsed_h = (datetime.now(tz=timezone.utc) - last_ts).total_seconds() / 3600
        return elapsed_h >= cadence_hours
    except Exception:
        return True


def _apify_mark_run():
    _APIFY_CADENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _APIFY_CADENCE_FILE.write_text(
        json.dumps({"last_run": datetime.now(tz=timezone.utc).isoformat()}),
        encoding="utf-8",
    )


def _collect_apify(cfg: dict) -> list[dict]:
    """Scraping de posts recientes en IG y TT via Apify actors."""
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        _log("[research] INFO: sin APIFY_TOKEN, saltando scraping IG/TT")
        return []

    try:
        from apify_client import ApifyClient  # type: ignore
    except ImportError:
        _log("[research] WARN: apify-client no instalado (pip install apify-client)")
        return []

    apify_cfg = cfg.get("apify", {})
    cadence_h = int(apify_cfg.get("instagram_profile_scraper", {}).get("cadence_hours", 48))
    if not _apify_cadence_ok(cadence_h):
        _log(f"[research] Apify: cadencia {cadence_h}h no cumplida, omitiendo scrape")
        return []
    ig_cfg    = apify_cfg.get("instagram_profile_scraper", {})
    tt_cfg    = apify_cfg.get("tiktok_profile_scraper", {})
    ig_handles = ig_cfg.get("benchmark_handles", [])
    tt_handles = tt_cfg.get("benchmark_handles", [])
    ig_limit   = ig_cfg.get("max_posts_per_run", 20)
    tt_limit   = tt_cfg.get("max_videos_per_run", 15)

    client  = ApifyClient(token)
    signals = []
    now_ts  = datetime.now(tz=timezone.utc).isoformat()

    # --- Instagram ---
    if ig_handles:
        try:
            run = client.actor("apify/instagram-profile-scraper").call(
                run_input={"usernames": ig_handles, "resultsLimit": ig_limit},
                timeout_secs=180,
            )
            for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                handle = item.get("username", "")
                for post in (item.get("latestPosts") or [])[:5]:
                    url = post.get("url", "")
                    if not url:
                        continue
                    caption = (post.get("caption") or "").strip()
                    signals.append({
                        "source_type": "ig",
                        "source":      f"ig@{handle}",
                        "title":       caption[:80] or f"IG post @{handle}",
                        "url":         url,
                        "summary":     caption[:300],
                        "published":   post.get("timestamp", now_ts),
                        "tags":        json.dumps(["instagram", "apify"]),
                        "likes":       post.get("likesCount", 0),
                        "comments":    post.get("commentsCount", 0),
                    })
        except Exception as e:
            _log(f"[research] WARN Apify IG: {e}")

    # --- TikTok ---
    if tt_handles:
        try:
            run = client.actor("clockworks/tiktok-profile-scraper").call(
                run_input={"profiles": tt_handles, "resultsPerPage": tt_limit},
                timeout_secs=180,
            )
            for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                url = item.get("webVideoUrl", "")
                if not url:
                    continue
                text = (item.get("text") or "").strip()
                signals.append({
                    "source_type": "tt",
                    "source":      "tiktok_apify",
                    "title":       text[:80] or "TikTok video",
                    "url":         url,
                    "summary":     text[:300],
                    "published":   item.get("createTimeISO", now_ts),
                    "tags":        json.dumps(["tiktok", "apify"]),
                    "plays":       item.get("playCount", 0),
                    "likes":       item.get("diggCount", 0),
                    "shares":      item.get("shareCount", 0),
                })
        except Exception as e:
            _log(f"[research] WARN Apify TT: {e}")

    _apify_mark_run()
    _log(f"[research] Apify: {len(signals)} posts (IG+TT)")
    return signals


# ---------------------------------------------------------------------------
# Deduplicacion
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _hash_signal(s: dict) -> str:
    norm = _normalize(s.get("title", "")) + _normalize(s.get("url", ""))
    return hashlib.sha256(norm.encode()).hexdigest()


def _dedupe(raw: list[dict], db: sqlite3.Connection) -> list[dict]:
    existing_hashes: set[str] = set()
    for tbl in ("signals_ig", "signals_tt", "signals_rss", "signals_news", "signals_trends"):
        try:
            rows = db.execute(f"SELECT hash_norm FROM {tbl}").fetchall()
            existing_hashes.update(r[0] for r in rows)
        except sqlite3.OperationalError:
            pass

    seen: set[str] = set()
    new: list[dict] = []
    for s in raw:
        h = _hash_signal(s)
        if h not in existing_hashes and h not in seen:
            s["_hash"] = h
            seen.add(h)
            new.append(s)
    return new


# ---------------------------------------------------------------------------
# LLM: clasificar + clusterizar + puntuar
# ---------------------------------------------------------------------------

def _llm_process(signals: list[dict], nichos: list[str]) -> tuple[list[dict], float]:
    try:
        router = load_router()
    except Exception as e:
        _log(f"[research] ERROR cargando router: {e}")
        return [], 0.0

    # Formatear senales de forma compacta para el prompt
    lines = []
    for i, s in enumerate(signals[:80]):  # max 80 senales por llamada
        pub = s.get("published", "")[:10]
        lines.append(f"[{i}] {s['source_type'].upper()} | {s['source']} | {pub} | {s['title'][:80]}")
        if s.get("summary"):
            lines.append(f"     {s['summary'][:120]}")

    user_msg = (
        f"Nichos a cubrir: {', '.join(nichos)}\n\n"
        f"Senales ({len(lines[:80])} entradas, mas recientes primero):\n"
        + "\n".join(lines)
    )

    try:
        resp = router.call(
            task="research.extract_structured",
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
        )
        raw_json = resp.text.strip()
        # Limpiar markdown fences si las hubiera
        if raw_json.startswith("```"):
            raw_json = "\n".join(raw_json.splitlines()[1:])
            raw_json = raw_json.rstrip("`").strip()

        data = json.loads(raw_json)
        shortlist = data.get("shortlist", [])
        _log(f"[research] LLM shortlist={len(shortlist)}  costo=${resp.cost_usd:.4f}")
        return shortlist, resp.cost_usd

    except json.JSONDecodeError as e:
        _log(f"[research] ERROR parseando JSON del LLM: {e}")
        return [], 0.0
    except Exception as e:
        _log(f"[research] ERROR LLM: {e}")
        return [], 0.0


# ---------------------------------------------------------------------------
# Escritura a DB
# ---------------------------------------------------------------------------

def _write_signals(db: sqlite3.Connection, signals: list[dict], ciclo_ts: str):
    now = ciclo_ts
    for s in signals:
        try:
            h  = s["_hash"]
            st = s["source_type"]
            if st == "rss":
                db.execute(
                    "INSERT OR IGNORE INTO signals_rss "
                    "(hash_norm, feed_name, feed_url, title, link, summary, published, tags, scraped_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (h, s["source"], s.get("url",""), s["title"],
                     s.get("url",""), s.get("summary",""),
                     s.get("published",""), s.get("tags","[]"), now)
                )
            elif st == "news":
                db.execute(
                    "INSERT OR IGNORE INTO signals_news "
                    "(hash_norm, query, title, url, snippet, low_confidence, scraped_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (h, s.get("query",""), s["title"], s.get("url",""),
                     s.get("summary",""), s.get("low_conf", 0), now)
                )
            elif st == "trends":
                db.execute(
                    "INSERT OR IGNORE INTO signals_trends "
                    "(keyword, geo, scraped_at) VALUES (?,?,?)",
                    (s["title"], "CO", now)
                )
            elif st == "ig":
                caption = s.get("summary", "")
                db.execute(
                    "INSERT OR IGNORE INTO signals_ig "
                    "(hash_norm, source, post_url, caption, hook_text, likes, comments, scraped_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (h, s["source"], s["url"], caption,
                     caption.split("\n")[0][:100],
                     s.get("likes", 0), s.get("comments", 0), now)
                )
            elif st == "tt":
                desc = s.get("summary", "")
                db.execute(
                    "INSERT OR IGNORE INTO signals_tt "
                    "(hash_norm, source, video_url, description, hook_text, plays, likes, shares, scraped_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (h, s["source"], s["url"], desc,
                     desc.split("\n")[0][:100],
                     s.get("plays", 0), s.get("likes", 0), s.get("shares", 0), now)
                )
        except Exception as e:
            _log(f"[research] WARN escribiendo senal: {e}")
    db.commit()


def _write_clusters(db: sqlite3.Connection, shortlist: list[dict], ciclo_ts: str):
    import uuid
    for item in shortlist:
        try:
            db.execute(
                "INSERT INTO signals_clustered "
                "(cluster_id, nicho, tema, angulo, score, formato_sugerido, "
                " ethics_risk, low_confidence, source_ids, source_tables, fuentes_json, ciclo_ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    item.get("nicho", ""),
                    item.get("tema", ""),
                    item.get("angulo", ""),
                    float(item.get("score", 0)),
                    item.get("formato_sugerido", "carrusel"),
                    item.get("ethics_risk", "low"),
                    0,
                    json.dumps(item.get("signal_indices", [])),
                    "[]",
                    json.dumps(item.get("fuentes", [])),
                    ciclo_ts,
                )
            )
        except Exception as e:
            _log(f"[research] WARN escribiendo cluster: {e}")
    db.commit()


def _write_cycle(db, ciclo_ts, trigger, nichos, raw, new_signals, shortlist, cost):
    try:
        db.execute(
            "INSERT OR IGNORE INTO research_cycles "
            "(ciclo_ts, trigger, nichos, signals_raw, signals_deduped, "
            " clusters_total, shortlist_count, cost_usd, status) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (ciclo_ts, trigger, json.dumps(nichos),
             len(raw), len(new_signals), len(shortlist), len(shortlist),
             cost, "ok")
        )
        db.commit()
    except Exception as e:
        _log(f"[research] WARN escribiendo ciclo: {e}")


def _startup_health_check() -> None:
    """Loguea presencia de API keys criticas y alerta a Telegram si faltan."""
    checks = {
        "TAVILY_API_KEY":     bool(os.environ.get("TAVILY_API_KEY")),
        "PERPLEXITY_API_KEY": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "APIFY_TOKEN":        bool(os.environ.get("APIFY_TOKEN")),
    }
    summary = " ".join(f"{k}={'OK' if v else 'MISSING'}" for k, v in checks.items())
    _log(f"[research] startup api_keys: {summary}")

    if not checks["TAVILY_API_KEY"] and not checks["PERPLEXITY_API_KEY"]:
        _log("[research] WARN: sin TAVILY ni PERPLEXITY — solo DuckDuckGo (fallback)")
        _notify_telegram(
            "Nolan WARN: research sin TAVILY ni PERPLEXITY. Solo DuckDuckGo "
            "como fallback (calidad degradada)."
        )


def _check_research_degraded(db: sqlite3.Connection) -> None:
    """Alerta si shortlist_count < 3 por 5 ciclos seguidos."""
    try:
        rows = db.execute(
            "SELECT shortlist_count FROM research_cycles "
            "ORDER BY ciclo_ts DESC LIMIT 5"
        ).fetchall()
        if len(rows) >= 5 and all((r[0] or 0) < 3 for r in rows):
            _log("[research] ALERT: 5 ciclos consecutivos con shortlist < 3")
            _notify_telegram(
                "Nolan ALERT: research degradado. 5 ciclos seguidos con < 3 "
                "temas en shortlist. Sistema vive del evergreen — revisar APIs."
            )
    except Exception as e:
        _log(f"[research] WARN degraded check: {e}")


def _notify_telegram(text: str) -> None:
    token = os.environ.get("HERMES_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat  = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not (token and chat):
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text},
            timeout=15,
        )
    except Exception:
        pass


def _reangle_evergreen(t: dict, evergreen_id: str) -> tuple[str, str] | None:
    """
    Genera un nuevo angulo + hook para un tema evergreen que ya se uso antes.

    Carga los hooks de las ultimas 3 piezas con el mismo evergreen_id y los pasa
    al LLM como negative examples para forzar diferenciacion. Si la DB no existe
    o no hay angulos previos, devuelve None (se usa angulo_propuesto original).

    Costo: ~$0.005/llamada (modelo cheap via router task 'strategy.reangle_evergreen').
    """
    if not PIECES_DB_PATH.exists():
        return None
    try:
        with sqlite3.connect(PIECES_DB_PATH) as pc:
            rows = pc.execute(
                "SELECT hook FROM pieces "
                "WHERE evergreen_id = ? AND hook IS NOT NULL AND hook != '' "
                "ORDER BY created_at DESC LIMIT 3",
                (evergreen_id,),
            ).fetchall()
        prev_angles = [r[0] for r in rows if r[0]]
    except Exception as e:
        _log(f"[research] WARN reangle query: {e}")
        return None

    if not prev_angles:
        return None

    try:
        router = load_router()
        prompt = (
            "Re-angula este tema evergreen para Sapiens (academia IA, audiencia "
            f"{t.get('nicho','')}).\n"
            f"Tema: {t.get('tema','')}\n"
            f"Conexion metodo: {t.get('conexion_metodo','')}\n"
            f"Angulo original: {t.get('angulo_propuesto','')}\n\n"
            "Angulos PREVIOS ya publicados (NO repetir, busca uno distinto):\n"
            + "\n".join(f"- {a}" for a in prev_angles)
            + "\n\nDevuelve SOLO JSON valido:\n"
              '{"angulo": "nuevo angulo distinto, 1 frase", "hook": "hook breve para opening"}'
        )
        resp = router.call(
            task="strategy.reangle_evergreen",
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.text.strip()
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:]).rstrip("`").strip()
        data = json.loads(text)
        new_angle = (data.get("angulo") or "").strip()
        new_hook  = (data.get("hook") or "").strip()
        if new_angle:
            _log(f"[research] reangle evergreen={evergreen_id}: '{new_angle[:80]}'")
            return (new_angle, new_hook)
    except Exception as e:
        _log(f"[research] WARN reangle LLM: {e}")
    return None


def _fill_from_evergreen(shortlist: list[dict], nichos: list[str]) -> list[dict]:
    """
    Completa el shortlist con temas evergreen curados si hay < 3 temas.

    Cambios respecto a la version original (anti-repeticion P0.5):
      - Filtra por evergreen_id (no por topic textual) — la columna `topic` en
        `pieces` viene del tema, no del id evergreen.
      - Ordena por antiguedad de ultimo uso (`freshness_score`) con random
        tie-break — rompe el orden estable del YAML que servia siempre el #1.
      - Cooldown configurable via NOLAN_EVERGREEN_COOLDOWN_DAYS (default 14).
      - Marca cada tema añadido con `evergreen_id` para que dedup downstream
        pueda hacer match exacto.
    """
    if not EVERGREEN_PATH.exists():
        _log("[research] WARN: evergreen_topics.yaml no encontrado, saltando floor")
        return []

    try:
        with open(EVERGREEN_PATH, encoding="utf-8") as f:
            ev_data = yaml.safe_load(f)
        ev_topics = ev_data.get("temas", [])
    except Exception as e:
        _log(f"[research] WARN cargando evergreen_topics.yaml: {e}")
        return []

    cooldown_days = int(os.environ.get("NOLAN_EVERGREEN_COOLDOWN_DAYS", "14"))

    # Ultimo uso por evergreen_id desde pieces.sqlite
    last_used: dict[str, str] = {}
    used_ev_ids: set[str] = set()
    if PIECES_DB_PATH.exists():
        try:
            with sqlite3.connect(PIECES_DB_PATH) as pc:
                for eid, last in pc.execute(
                    "SELECT evergreen_id, MAX(created_at) FROM pieces "
                    "WHERE evergreen_id IS NOT NULL AND evergreen_id != '' "
                    "GROUP BY evergreen_id"
                ):
                    if eid:
                        last_used[eid] = last
                cutoff_iso = (
                    datetime.now(tz=timezone.utc) - timedelta(days=cooldown_days)
                ).isoformat()
                used_ev_ids = {
                    eid for eid, last in last_used.items()
                    if last and last >= cutoff_iso
                }
        except Exception as e:
            _log(f"[research] WARN evergreen usage query: {e}")

    import random

    def freshness_score(t: dict) -> float:
        eid = t.get("id", "")
        if eid not in last_used:
            return 1_000_000.0 + random.random()  # nunca usado: top
        try:
            iso = last_used[eid].replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(tz=timezone.utc) - dt).days + random.random()
        except Exception:
            return random.random()

    ev_topics_sorted = sorted(ev_topics, key=freshness_score, reverse=True)

    existing_temas = {s.get("tema", "").lower() for s in shortlist}
    needed = 3 - len(shortlist)
    added: list[dict] = []

    for t in ev_topics_sorted:
        if needed <= 0:
            break
        if t.get("nicho") not in nichos:
            continue
        if t.get("tema", "").lower() in existing_temas:
            continue
        ev_id = t.get("id", "")
        if ev_id in used_ev_ids:
            continue

        # Re-angulacion LLM si el tema ya se uso antes (fuera de la ventana
        # de cooldown pero presente en historial). Evita publicar 2 piezas
        # con el mismo angulo_propuesto del YAML.
        angulo = t.get("angulo_propuesto", "")
        hook   = ""
        if ev_id in last_used:
            angulo, hook = _reangle_evergreen(t, ev_id) or (angulo, "")

        added.append({
            "tema":              t["tema"],
            "nicho":             t["nicho"],
            "pillar":            t.get("pillar", "tecnica_densa"),
            "angulo":            angulo,
            "hook":              hook or angulo,
            "score":             0.5,
            "formato_sugerido":  t.get("formato_sugerido", "carrusel"),
            "ethics_risk":       "low",
            "fuentes":           [],
            "low_confidence":    False,
            "conexion_metodo":   t.get("conexion_metodo", ""),
            "source":            "evergreen",
            "evergreen_id":      ev_id,
        })
        existing_temas.add(t["tema"].lower())
        needed -= 1

    if needed > 0 and not added:
        _log(
            f"[research] WARN: todos los evergreen del nicho usados en ultimos "
            f"{cooldown_days} dias — shortlist puede quedar vacio"
        )

    return added


def _load_existing_shortlist(db: sqlite3.Connection, nichos: list[str]) -> list[dict]:
    try:
        placeholders = ",".join("?" * len(nichos))
        rows = db.execute(
            f"SELECT tema, nicho, angulo, score, formato_sugerido, ethics_risk, fuentes_json "
            f"FROM signals_clustered "
            f"WHERE nicho IN ({placeholders}) AND used_in_piece IS NULL "
            f"ORDER BY score DESC LIMIT 12",
            nichos
        ).fetchall()
        return [
            {"tema": r[0], "nicho": r[1], "angulo": r[2], "score": r[3],
             "formato_sugerido": r[4], "ethics_risk": r[5],
             "fuentes": json.loads(r[6] or "[]")}
            for r in rows
        ]
    except Exception as e:
        _log(f"[research] WARN cargando shortlist existente: {e}")
        return []


# ---------------------------------------------------------------------------
# Init DB
# ---------------------------------------------------------------------------

def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    if SCHEMA_SQL.exists():
        schema = SCHEMA_SQL.read_text(encoding="utf-8")
        db.executescript(schema)
    db.commit()
    return db


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _parse_date(date_str: str):
    if not date_str:
        return None
    import email.utils
    try:
        t = email.utils.parsedate_to_datetime(date_str)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            t = datetime.strptime(date_str[:19], fmt[:len(date_str)])
            return t.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _log(msg: str):
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} {msg}"
    print(line, file=sys.stderr)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
