"""
Ethics Gate de Nolan — semáforo rojo/amarillo/verde sobre texto de piezas.

Importar:
    from sapiens.ethics_gate import EthicsGate, EthicsResult, load_gate

Aplica las reglas de config/ethics.yaml sobre texto plano de slides,
captions y scripts antes de que el paquete salga a staging/.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(os.environ.get("NOLAN_PROJECT_ROOT", Path(__file__).parent.parent))


@dataclass
class EthicsResult:
    status: str          # "green" | "yellow" | "red"
    rule_id: str = ""
    description: str = ""
    matched_text: str = ""


class EthicsGate:
    """Aplica las reglas de ethics.yaml. Stateless — instanciar una vez y reutilizar."""

    def __init__(self, cfg: dict):
        self.red = cfg.get("red", [])
        self.yellow = cfg.get("yellow", [])

    def check(self, texts: list[str], sources_available: bool = False) -> EthicsResult:
        """
        Evalúa una lista de strings (slides + caption + script).

        Args:
            texts: Textos a revisar.
            sources_available: True si sources.md existe con citas (exime unsourced_claims).
        Returns:
            EthicsResult — status="green" si ninguna regla dispara.
        """
        combined = "\n".join(t for t in texts if t)

        for rule in self.red:
            hit = self._eval_rule(rule, combined, sources_available)
            if hit:
                return EthicsResult(
                    status="red",
                    rule_id=rule["id"],
                    description=rule.get("description", ""),
                    matched_text=hit,
                )

        for rule in self.yellow:
            if rule.get("requires_sources_md") and sources_available:
                continue
            hit = self._eval_rule(rule, combined, sources_available)
            if hit:
                return EthicsResult(
                    status="yellow",
                    rule_id=rule["id"],
                    description=rule.get("description", ""),
                    matched_text=hit,
                )

        return EthicsResult(status="green")

    # ------------------------------------------------------------------

    def _eval_rule(self, rule: dict, text: str, sources_available: bool) -> str:
        flags = re.IGNORECASE if rule.get("case_insensitive") else 0

        if "competitor_names" in rule:
            return self._check_cooccurrence(rule, text, flags)

        if "patterns_unicode" in rule:
            for raw in rule.get("patterns_unicode", []):
                pattern = self._js_unicode_to_python(raw)
                try:
                    if re.search(pattern, text, re.UNICODE):
                        return "<emoji detectado>"
                except re.error:
                    pass

        for pattern in rule.get("patterns", []):
            try:
                m = re.search(pattern, text, flags)
                if m:
                    return m.group(0)
            except re.error:
                pass

        return ""

    def _check_cooccurrence(self, rule: dict, text: str, flags: int) -> str:
        """Regla competitor_name_attack: nombre + palabra de ataque en ±40 palabras."""
        window = 40
        for name in rule.get("competitor_names", []):
            if not re.search(re.escape(name), text, flags):
                continue
            for kw in rule.get("attack_keywords", []):
                pattern = (
                    f"(?:{re.escape(name)}"
                    f"(?:\\s+\\S+){{0,{window}}}"
                    f"\\s+{re.escape(kw)}"
                    f"|{re.escape(kw)}"
                    f"(?:\\s+\\S+){{0,{window}}}"
                    f"\\s+{re.escape(name)})"
                )
                if re.search(pattern, text, flags | re.DOTALL):
                    return f"{name} + {kw}"
        return ""

    @staticmethod
    def _js_unicode_to_python(pattern: str) -> str:
        """Convierte \\u{1F600} (JS/YAML) a \\U0001F600 (Python regex)."""
        def repl(m: re.Match) -> str:
            code = int(m.group(1), 16)
            return f"\\U{code:08X}"
        return re.sub(r"\\u\{([0-9A-Fa-f]+)\}", repl, pattern)


def load_gate() -> EthicsGate:
    """Carga EthicsGate desde config/ethics.yaml del proyecto."""
    with open(PROJECT_ROOT / "config" / "ethics.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return EthicsGate(cfg)
