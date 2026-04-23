"""
nolan-decide-format — decide formato y arquetipo desde un tema y nicho.

Uso:
    python decide_format.py --topic "ICFES lectura crítica método 3 pasos" \\
                            --niche jovenes_preicfes [--hook "..."] [--dry-run]

Salida: brief YAML impreso en stdout, listo para pasar a nolan-produce-carrusel.

Lógica: reglas declarativas primero → LLM solo si quedan ambigüedades.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent
))
sys.path.insert(0, str(PROJECT_ROOT))

from sapiens.nolan_llm_router import load_router   # noqa: E402

# ---------------------------------------------------------------------------
# Señales de formato (regex sobre el topic)
# ---------------------------------------------------------------------------

_MATH_RE = re.compile(
    r"\$\$|derivada|integral|reacción\s+química|cinética|binomio|ecuación|serie\s+de|"
    r"límite\s+(de|cuando)|probabilidad\s+(condicional|de)",
    re.IGNORECASE,
)
_EDITORIAL_RE = re.compile(
    r"por qué creemos|nuestra postura|mi experiencia como|me preguntan mucho",
    re.IGNORECASE,
)
_NARRATIVE_RE = re.compile(
    r"caso de\b|historia de\b|cómo pasó\b|cuando .{3,30} logró",
    re.IGNORECASE,
)

# Arquetipos para carrusel
_COMPARATIVE_RE = re.compile(r"\bvs\b|comparar|diferencia entre|mejor que", re.IGNORECASE)
_FRAMEWORK_RE = re.compile(
    r"paso\s+\d|pasos|método de|framework|cómo (hacer|lograr|resolver|preparar)",
    re.IGNORECASE,
)
_SIGNALS_RE = re.compile(
    r"\d+\s+(razones|señales|tips|errores|formas|factores|claves)",
    re.IGNORECASE,
)
_THESIS_RE = re.compile(
    r"por qué\b|lo que nadie|la verdad sobre|argumento|tesis",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Lógica de decisión
# ---------------------------------------------------------------------------

def decide_format_by_rules(topic: str) -> dict | None:
    """Devuelve dict con keys format/archetype/method/rule, o None si ambiguo."""
    if _MATH_RE.search(topic):
        return {"format": "animacion", "archetype": "ad_hoc", "method": "rules", "rule": "math_signals"}
    if _EDITORIAL_RE.search(topic):
        return {"format": "talking_head", "archetype": "ad_hoc", "method": "rules", "rule": "editorial"}
    if _NARRATIVE_RE.search(topic):
        return {"format": "voiceover_broll", "archetype": "ad_hoc", "method": "rules", "rule": "narrative"}
    return None


def decide_archetype_by_rules(topic: str) -> str:
    if _COMPARATIVE_RE.search(topic):
        return "comparativa"
    if _FRAMEWORK_RE.search(topic):
        return "framework"
    if _SIGNALS_RE.search(topic):
        return "senales"
    if _THESIS_RE.search(topic):
        return "tesis"
    return "framework"   # default razonable para educación


def decide_format_llm(topic: str, niche: str, hook: str) -> dict:
    """Delega al LLM cuando las reglas no alcanzan confianza > 0.7."""
    router = load_router()
    user = (
        "Decide el formato óptimo para esta pieza de contenido Instagram educativo.\n"
        f"Tema: {topic}\nNicho: {niche}\nHook candidato: {hook or '(sin hook aún)'}\n\n"
        "Formatos posibles: carrusel, animacion, voiceover_broll, talking_head.\n"
        "Arquetipos para carrusel: senales, tesis, comparativa, framework.\n"
        "Responde SOLO con JSON: "
        '{"format": "...", "archetype": "...", "rationale": "..."}'
    )
    resp = router.call(
        task="strategy.decide_format",
        messages=[{"role": "user", "content": user}],
    )
    try:
        data = json.loads(resp.text)
        return {
            "format": data["format"],
            "archetype": data.get("archetype", "framework"),
            "method": "llm",
            "rule": "llm_decision",
        }
    except (json.JSONDecodeError, KeyError):
        return {"format": "carrusel", "archetype": "framework", "method": "llm_fallback", "rule": ""}


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Decide formato y arquetipo para una pieza Nolan")
    ap.add_argument("--topic", required=True, help="Descripción del tema")
    ap.add_argument("--niche", required=True,
                    choices=["jovenes_preicfes", "padres", "adultos_ia", "pymes", "cruzado_l1_l2"])
    ap.add_argument("--hook", default="", help="Hook candidato (opcional)")
    ap.add_argument("--dry-run", action="store_true",
                    help="No llama al LLM aunque las reglas sean ambiguas")
    args = ap.parse_args()

    # Intento con reglas
    result = decide_format_by_rules(args.topic)

    if result is None:
        # Default carrusel — arquetipo por reglas
        archetype = decide_archetype_by_rules(args.topic)
        result = {
            "format": "carrusel",
            "archetype": archetype,
            "method": "rules",
            "rule": "default_carrusel",
        }

    # Si quedó ad_hoc en carrusel y no es dry-run, consultar LLM
    if result["format"] == "carrusel" and result.get("archetype") == "ad_hoc" and not args.dry_run:
        result = decide_format_llm(args.topic, args.niche, args.hook)

    today = datetime.now().strftime("%Y-%m-%d")
    slug = _slugify(args.topic)[:45]
    piece_id = f"{today}-{slug}"

    niche_tone = {
        "jovenes_preicfes": "jovenes_directo_sin_paternalismo",
        "padres": "padres_empatico_sin_culpabilizar",
        "adultos_ia": "adultos_pragmatico_roi",
        "pymes": "pymes_problema_solucion",
        "cruzado_l1_l2": "cruzado_adaptativo",
    }

    brief = {
        "piece_id": piece_id,
        "niche": args.niche,
        "format": result["format"],
        "archetype": result.get("archetype", "framework"),
        "hook": args.hook or "",
        "thesis": args.topic,
        "pillars": [],
        "sources": [],
        "tone_calibration": niche_tone.get(args.niche, args.niche),
        "slides_count_estimate": 7,
        "production_skill": f"nolan-produce-{result['format']}",
        "ethics_risk_estimate": "low",
        "estimated_production_cost_usd": 0.12,
        "decision_method": result.get("method", "rules"),
    }

    print(yaml.dump(brief, allow_unicode=True, default_flow_style=False, sort_keys=False))
    print(f"# decisión: {result['method']} → format={result['format']}, archetype={result.get('archetype')}",
          file=sys.stderr)


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[áàäâ]", "a", text)
    text = re.sub(r"[éèëê]", "e", text)
    text = re.sub(r"[íìïî]", "i", text)
    text = re.sub(r"[óòöô]", "o", text)
    text = re.sub(r"[úùüû]", "u", text)
    text = re.sub(r"ñ", "n", text)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


if __name__ == "__main__":
    main()
