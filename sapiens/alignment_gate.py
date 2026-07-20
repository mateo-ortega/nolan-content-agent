"""
sapiens.alignment_gate — Filtro de calidad positivo Sapiens.

Complementa ethics_gate.py:
  - Ethics  = "no hagas dano"  (regex prohibidas, semaforo defensivo)
  - Aligment = "haz bien"      (cuotas, pillar, arquetipo, vocabulario resonante)

Cuatro checks por pieza:
  1. _check_pillar_allowed     pillar de la pieza ∈ pillars permitidos en fase actual
  2. _check_pillar_quota       no exceder cuota semanal del pillar (rotacion)
  3. _check_archetype_declared archetype ∈ valid set para el formato
  4. _check_resonant_vocabulary caption debe usar al menos 1 frase resonante del nicho

Salida: AlignmentResult(status, checks).
  status="red"    al menos 1 check fallo con severidad red  → bloquea publicacion
  status="yellow" al menos 1 check fallo con severidad yellow → no bloquea, anota
  status="green"  todo paso
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from sapiens._paths import PROJECT_ROOT, pieces_db_path


def _strip_accents_lower(text: str) -> str:
    text = text.lower()
    for src, dst in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),
                     ("ñ","n"),("ü","u")]:
        text = text.replace(src, dst)
    return text


@dataclass
class AlignmentCheck:
    id: str
    passed: bool
    severity: str = "green"     # "green" | "yellow" | "red"
    reason: str = ""


@dataclass
class AlignmentResult:
    status: str                                  # "green" | "yellow" | "red"
    checks: list[AlignmentCheck] = field(default_factory=list)


class AlignmentGate:
    """Aplica reglas de alignment.yaml + brand_phase.yaml. Stateless."""

    def __init__(self, cfg: dict, brand_phase: dict, db_path: Path | None = None):
        self.cfg = cfg
        self.phase = brand_phase
        self.db_path = db_path or pieces_db_path()

    # ── API publica ─────────────────────────────────────────────────────────

    def check(self, piece_meta: dict, texts: list[str]) -> AlignmentResult:
        checks = [
            self._check_pillar_allowed(piece_meta),
            self._check_pillar_quota(piece_meta),
            self._check_archetype_declared(piece_meta),
            self._check_resonant_vocabulary(texts, piece_meta.get("niche", "")),
            self._check_distance_phrases(texts, piece_meta.get("niche", "")),
        ]

        # status = peor severidad encontrada
        if any(c.severity == "red" for c in checks):
            status = "red"
        elif any(c.severity == "yellow" for c in checks):
            status = "yellow"
        else:
            status = "green"
        return AlignmentResult(status=status, checks=checks)

    # ── Checks individuales ─────────────────────────────────────────────────

    def _current_phase_key(self) -> str:
        try:
            end = datetime.fromisoformat(self.phase.get("phase_1_3_end", "2026-07-25"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            return "phase_1_3" if datetime.now(tz=timezone.utc) <= end else "phase_4_plus"
        except Exception:
            return "phase_1_3"

    def _check_pillar_allowed(self, meta: dict) -> AlignmentCheck:
        pillar = (meta.get("pillar") or "").strip()
        if not pillar:
            return AlignmentCheck(
                id="pillar_allowed", passed=False, severity="yellow",
                reason="pieza sin pillar declarado",
            )
        phase_key = self._current_phase_key()
        allowed = self.phase.get("pillars_by_phase", {}).get(phase_key, [])
        if pillar in allowed:
            return AlignmentCheck(id="pillar_allowed", passed=True)
        return AlignmentCheck(
            id="pillar_allowed", passed=False, severity="red",
            reason=f"pillar '{pillar}' no permitido en {phase_key} (permitidos: {allowed})",
        )

    def _check_pillar_quota(self, meta: dict) -> AlignmentCheck:
        pillar = (meta.get("pillar") or "").strip()
        if not pillar or not self.db_path.exists():
            return AlignmentCheck(id="pillar_quota", passed=True)

        quotas = self.cfg.get("pillar_quotas", {})
        window = int(quotas.get("window_days", 7))
        caps = quotas.get("caps", {}).get(pillar, {})
        yellow_above = caps.get("yellow_above", 99)
        red_above    = caps.get("red_above", 99)

        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=window)).isoformat()
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM pieces "
                    "WHERE pillar = ? AND created_at >= ?",
                    (pillar, cutoff),
                ).fetchone()
            count = int(row[0]) if row else 0
        except sqlite3.Error as e:
            print(f"[alignment] WARN pillar_quota query: {e}", file=sys.stderr)
            return AlignmentCheck(id="pillar_quota", passed=True)

        if count >= red_above:
            return AlignmentCheck(
                id="pillar_quota", passed=False, severity="red",
                reason=f"pillar '{pillar}' tiene {count} piezas en {window}d (red>={red_above})",
            )
        if count >= yellow_above:
            return AlignmentCheck(
                id="pillar_quota", passed=False, severity="yellow",
                reason=f"pillar '{pillar}' tiene {count} piezas en {window}d (yellow>={yellow_above})",
            )
        return AlignmentCheck(id="pillar_quota", passed=True)

    def _check_archetype_declared(self, meta: dict) -> AlignmentCheck:
        fmt = meta.get("format", "")
        archetype = (meta.get("archetype") or "").strip()
        valid = self.cfg.get("archetypes", {}).get(fmt, [])
        if not valid:
            return AlignmentCheck(id="archetype_declared", passed=True)
        if archetype == "ad_hoc" or not archetype:
            return AlignmentCheck(
                id="archetype_declared", passed=False, severity="yellow",
                reason=f"archetype '{archetype or '<vacio>'}' indefinido para format={fmt}",
            )
        if archetype not in valid:
            return AlignmentCheck(
                id="archetype_declared", passed=False, severity="yellow",
                reason=f"archetype '{archetype}' no esta en validos {valid} para format={fmt}",
            )
        return AlignmentCheck(id="archetype_declared", passed=True)

    def _check_resonant_vocabulary(self, texts: list[str], niche: str) -> AlignmentCheck:
        keywords = self.cfg.get("resonant_keywords", {}).get(niche, [])
        if not keywords:
            return AlignmentCheck(id="resonant_vocabulary", passed=True)
        combined = _strip_accents_lower("\n".join(t for t in texts if t))
        if not combined:
            return AlignmentCheck(id="resonant_vocabulary", passed=True)
        for kw in keywords:
            if _strip_accents_lower(kw) in combined:
                return AlignmentCheck(id="resonant_vocabulary", passed=True)
        return AlignmentCheck(
            id="resonant_vocabulary", passed=False, severity="yellow",
            reason=f"caption no usa ninguna frase resonante del nicho '{niche}'",
        )

    def _check_distance_phrases(self, texts: list[str], niche: str) -> AlignmentCheck:
        phrases = self.cfg.get("distance_phrases", {}).get(niche, [])
        if not phrases:
            return AlignmentCheck(id="distance_phrases", passed=True)
        combined = _strip_accents_lower("\n".join(t for t in texts if t))
        for ph in phrases:
            if _strip_accents_lower(ph) in combined:
                return AlignmentCheck(
                    id="distance_phrases", passed=False, severity="yellow",
                    reason=f"contiene frase que aleja: '{ph}'",
                )
        return AlignmentCheck(id="distance_phrases", passed=True)


def load_align_gate() -> AlignmentGate:
    """Carga AlignmentGate desde config/alignment.yaml + config/brand_phase.yaml."""
    align_path = PROJECT_ROOT / "config" / "alignment.yaml"
    phase_path = PROJECT_ROOT / "config" / "brand_phase.yaml"
    with open(align_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    with open(phase_path, encoding="utf-8") as f:
        brand_phase = yaml.safe_load(f) or {}
    return AlignmentGate(cfg, brand_phase)
