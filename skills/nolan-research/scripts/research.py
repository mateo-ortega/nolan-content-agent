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

SOURCES_CFG  = PROJECT_ROOT / "config" / "sources.yaml"
SCHEMA_SQL   = PROJECT_ROOT / "memory" / "schemas" / "trends.sql"
DB_PATH      = PROJECT_ROOT / "memory" / "trends.sqlite"
LOG_PATH     = PROJECT_ROOT / "logs" / "research.log"

ALL_NICHOS = ["jovenes_preicfes", "padres", "adultos_ia", "pymes"]

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

    # 1. Cargar config
    with open(SOURCES_CFG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 2. Init DB
    db = _init_db()

    # 3. Recolectar senales
    raw: list[dict] = []
    raw.extend(_collect_rss(cfg))
    raw.extend(_collect_google_trends(cfg))
    raw.extend(_collect_perplexity(cfg))   # no-op si falta PERPLEXITY_API_KEY
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

    # 6. Escribir a DB
    if not args.dry_run:
        _write_signals(db, new_signals, ciclo_ts)
        _write_clusters(db, shortlist, ciclo_ts)
        _write_cycle(db, ciclo_ts, args.trigger, nichos, raw, new_signals, shortlist, llm_cost)

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


def _collect_perplexity(cfg: dict) -> list[dict]:
    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        _log("[research] WARN: sin PERPLEXITY_API_KEY, saltando noticias Perplexity")
        return []

    queries = cfg.get("perplexity", {}).get("queries", [])
    max_q   = cfg.get("perplexity", {}).get("max_queries_per_cycle", 5)
    signals = []

    for query in queries[:max_q]:
        try:
            resp = httpx.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
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
            data = resp.json()
            citations = data.get("citations", [])
            low_conf  = 1 if not citations else 0
            content   = data["choices"][0]["message"]["content"]
            for cit in citations[:4]:
                signals.append({
                    "source_type": "news",
                    "source":      "perplexity",
                    "query":       query,
                    "title":       cit if isinstance(cit, str) else cit.get("title", query),
                    "url":         cit if isinstance(cit, str) else cit.get("url", ""),
                    "summary":     content[:300],
                    "published":   datetime.now(tz=timezone.utc).isoformat(),
                    "low_conf":    low_conf,
                    "tags":        json.dumps(["perplexity", "news"]),
                })
            time.sleep(1)
        except Exception as e:
            _log(f"[research] WARN Perplexity '{query}': {e}")

    _log(f"[research] Perplexity: {len(signals)} citas")
    return signals


def _collect_apify(cfg: dict) -> list[dict]:
    """Stub — activa cuando APIFY_TOKEN este disponible."""
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        _log("[research] INFO: sin APIFY_TOKEN, saltando scraping IG/TT (agregar a .env cuando disponible)")
        return []
    # TODO: implementar con apify_client cuando el token este disponible
    _log("[research] INFO: APIFY_TOKEN presente pero scraping IG/TT no implementado aun")
    return []


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
