"""
sapiens.dedup — Deduplicacion de temas/piezas para Nolan.

Tres capas de deteccion de repetido:

  1. is_duplicate_evergreen_id   match exacto contra evergreen items usados en
                                  los ultimos N dias (ventana configurable).
  2. is_duplicate_topic           Jaccard sobre tokens normalizados + Jaccard
                                  sobre n-gramas (bigramas) con stemming
                                  rudimentario espanol. Atrapa temas con
                                  vocabulario distinto pero misma idea.
  3. pillar_quota_exceeded        rota pilares para no producir 7 piezas
                                  seguidas del mismo (cuotas en brand-profile).

find_non_duplicate() corre los 3 checks sobre un shortlist en orden de score
y devuelve el primer candidato limpio. Si todos fallan, devuelve None y el
caller (ciclo.sh) debe abortar el ciclo en vez de publicar duplicado.

DB: memory/pieces.sqlite (override via NOLAN_PIECES_DB_OVERRIDE para tests).
"""

from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sapiens._paths import pieces_db_path as _default_db_path


# Stopwords espanol (basico — suficiente para temas cortos de Sapiens)
_STOPWORDS = {
    "de", "el", "la", "los", "las", "un", "una", "y", "en", "con",
    "por", "para", "del", "al", "que", "se", "es", "son", "lo", "le",
    "su", "sus", "este", "esta", "ese", "esa", "no", "si", "tu", "te",
    "como", "ya", "muy", "mas", "pero", "o", "u",
}

# Sufijos para stem rudimentario espanol (orden importa: mas largos primero)
_SPANISH_STEM_SUFFIXES = (
    "emos", "iste", "imos", "amos", "aron", "eron", "ando", "iendo",
    "mente", "ado", "ido", "ada", "ida", "ar", "er", "ir",
    "as", "es", "os", "an", "en", "a", "o", "s",
)


def _strip_accents(text: str) -> str:
    for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),
                     ("ñ","n"),("ü","u")]:
        text = text.replace(src, dst)
    return text


def _stem_es(word: str) -> str:
    """Stem rudimentario: corta sufijo mas largo dejando >=3 chars de raiz."""
    for suf in _SPANISH_STEM_SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def topic_tokens(text: str) -> set[str]:
    """Set de tokens normalizados (lowercase, sin acentos, sin stopwords)."""
    text = _strip_accents(text.lower())
    return {w for w in re.findall(r"\w+", text) if len(w) > 2 and w not in _STOPWORDS}


def topic_ngrams(text: str) -> set[str]:
    """Unigramas (stemmed) + bigramas (stemmed) sobre topic_tokens."""
    raw = sorted(topic_tokens(text))
    stems = [_stem_es(w) for w in raw]
    grams: set[str] = set(stems)
    for i in range(len(stems) - 1):
        grams.add(f"{stems[i]}_{stems[i+1]}")
    return grams


def jaccard(a: set, b: set) -> float:
    if not (a and b):
        return 0.0
    return len(a & b) / len(a | b)


# ──────────────────────────────────────────────────────────────────────────────
# Checks individuales
# ──────────────────────────────────────────────────────────────────────────────

def is_duplicate_topic(
    topic: str,
    *,
    db_path: Path | None = None,
    jaccard_threshold: float = 0.55,
    ngrams_threshold: float = 0.40,
) -> tuple[bool, dict | None]:
    """Devuelve (True, info_match) si encuentra dup; (False, None) si no.

    Corre 2 metricas y dispara si CUALQUIERA pasa el umbral:
      - Jaccard sobre tokens crudos (umbral 0.55) — atrapa repeticion lexica.
      - Jaccard sobre n-gramas con stem (umbral 0.40) — atrapa repeticion
        conceptual con vocabulario distinto.
    """
    db_path = db_path or _default_db_path()
    if not db_path.exists():
        return (False, None)

    cand_tokens = topic_tokens(topic)
    cand_grams  = topic_ngrams(topic)
    if not cand_tokens:
        return (False, None)

    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT piece_id, topic, created_at FROM pieces "
                "WHERE topic IS NOT NULL AND topic != ''"
            ).fetchall()
    except sqlite3.Error as exc:
        print(f"[dedup] WARN consulta pieces: {exc}", file=sys.stderr)
        return (False, None)

    best: tuple[float, str, dict] = (0.0, "", {})
    for piece_id, existing_topic, created_at in rows:
        ext_tokens = topic_tokens(existing_topic or "")
        ext_grams  = topic_ngrams(existing_topic or "")
        if not ext_tokens:
            continue
        j_tok = jaccard(cand_tokens, ext_tokens)
        j_gra = jaccard(cand_grams, ext_grams)
        score = max(j_tok, j_gra)
        if score > best[0]:
            best = (
                score, "ngrams" if j_gra > j_tok else "tokens",
                {
                    "piece_id": piece_id,
                    "topic": existing_topic,
                    "created_at": created_at,
                    "jaccard_tokens": round(j_tok, 3),
                    "jaccard_ngrams": round(j_gra, 3),
                },
            )

    score, kind, info = best
    triggered = (
        (kind == "tokens" and score >= jaccard_threshold)
        or (kind == "ngrams" and score >= ngrams_threshold)
    )
    if triggered:
        info["matched_metric"] = kind
        info["matched_score"]  = round(score, 3)
        return (True, info)
    return (False, None)


def is_duplicate_evergreen_id(
    evergreen_id: str,
    *,
    db_path: Path | None = None,
    window_days: int = 14,
) -> tuple[bool, dict | None]:
    """True si ese evergreen_id ya fue usado en una pieza dentro de la ventana."""
    if not evergreen_id:
        return (False, None)
    db_path = db_path or _default_db_path()
    if not db_path.exists():
        return (False, None)
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=window_days)).isoformat()
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT piece_id, created_at FROM pieces "
                "WHERE evergreen_id = ? AND created_at >= ? "
                "ORDER BY created_at DESC LIMIT 1",
                (evergreen_id, cutoff),
            ).fetchone()
    except sqlite3.Error as exc:
        print(f"[dedup] WARN consulta evergreen_id: {exc}", file=sys.stderr)
        return (False, None)
    if row:
        return (True, {
            "piece_id": row[0],
            "created_at": row[1],
            "evergreen_id": evergreen_id,
        })
    return (False, None)


# Cuota maxima de piezas por pillar en ventana de N dias (default 7).
# Calibrado para ciclo de 1 pieza/dia con cuotas brand-profile fase 1-3:
#   tecnica_densa 40% → max 3/sem ; demostraciones_metodo 25% → 2/sem
#   filosofia_educativa 20% → 2/sem ; testimonios_video 15% → 1/sem
_DEFAULT_PILLAR_CAPS = {
    "tecnica_densa":         3,
    "demostraciones_metodo": 2,
    "filosofia_educativa":   2,
    "testimonios_video":     1,
}


def pillar_quota_exceeded(
    pillar: str,
    niche: str | None = None,  # noqa: ARG001 (reservado para futura cuota por nicho)
    *,
    db_path: Path | None = None,
    window_days: int = 7,
    max_count: int | None = None,
) -> tuple[bool, int]:
    """True si en ultimos window_days hubo >= max_count piezas de ese pillar."""
    if not pillar:
        return (False, 0)
    db_path = db_path or _default_db_path()
    if not db_path.exists():
        return (False, 0)
    cap = max_count if max_count is not None else _DEFAULT_PILLAR_CAPS.get(pillar, 3)
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=window_days)).isoformat()
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM pieces "
                "WHERE pillar = ? AND created_at >= ?",
                (pillar, cutoff),
            ).fetchone()
    except sqlite3.Error as exc:
        print(f"[dedup] WARN consulta pillar quota: {exc}", file=sys.stderr)
        return (False, 0)
    count = int(row[0]) if row else 0
    return (count >= cap, count)


# ──────────────────────────────────────────────────────────────────────────────
# Orquestador
# ──────────────────────────────────────────────────────────────────────────────

def find_non_duplicate(
    candidates: list[dict],
    *,
    db_path: Path | None = None,
    log: bool = True,
) -> dict | None:
    """Itera candidatos en orden y devuelve el primero que pasa los 3 checks.

    Cada candidato es un dict del shortlist de research (campos: tema, nicho,
    pillar, evergreen_id opcional, etc.). None si todos fallan.
    """
    for i, c in enumerate(candidates):
        tema = c.get("tema", "") or c.get("topic", "")
        eid  = c.get("evergreen_id", "")
        pillar = c.get("pillar", "")
        niche  = c.get("nicho", "")

        dup_ev, info_ev = is_duplicate_evergreen_id(eid, db_path=db_path)
        if dup_ev:
            if log:
                print(f"[dedup] candidato #{i} ({tema!r}) descartado: evergreen_id usado "
                      f"en {info_ev['created_at']}", file=sys.stderr)
            continue

        dup_t, info_t = is_duplicate_topic(tema, db_path=db_path)
        if dup_t:
            if log:
                print(f"[dedup] candidato #{i} ({tema!r}) descartado: dup topic "
                      f"({info_t['matched_metric']}={info_t['matched_score']}) "
                      f"vs {info_t['topic']!r}", file=sys.stderr)
            continue

        quota_full, count = pillar_quota_exceeded(pillar, niche, db_path=db_path)
        if quota_full:
            if log:
                print(f"[dedup] candidato #{i} ({tema!r}) descartado: cuota "
                      f"pillar={pillar} llena ({count} piezas en 7d)", file=sys.stderr)
            continue

        if log:
            print(f"[dedup] candidato #{i} ({tema!r}) ACEPTADO "
                  f"pillar={pillar} evergreen_id={eid or '-'}", file=sys.stderr)
        return c

    if log:
        print(f"[dedup] todos los {len(candidates)} candidatos descartados — "
              f"abortar ciclo", file=sys.stderr)
    return None
