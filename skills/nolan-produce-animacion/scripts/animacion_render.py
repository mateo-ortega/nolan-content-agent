"""
animacion_render.py — Manim entrypoint para el sistema de templates Sapiens.

Invocado por produce_animacion.py vía subprocess:
    ANIM_PARAMS_PATH=/staging/<piece_id>/anim_params.json \
    SAPIENS_THEME_DIR=/srv/sapiens-nolan/skills/sapiens-animacion \
    SAPIENS_LOGO_PATH=/srv/sapiens-nolan/skills/sapiens-animacion/sapiens_logo_wm.png \
    manim animacion_render.py SapiensAnimScene \
        -qh --fps 60 --resolution 1080,1920 --output_file animation.mp4 \
        --media_dir /staging/<piece_id>/media

La clase SapiensAnimScene NO sobreescribe setup() — la configuración de cámara
la hace BaseTemplate._setup_scene() para garantizar frame_width=9, frame_height=16.
"""

import json
import os
import sys
from pathlib import Path

# ── Resolver ruta a sapiens_theme (igual que en animacion_templates.py) ───────
_THEME_DIR = Path(os.environ.get(
    "SAPIENS_THEME_DIR",
    "/srv/sapiens-nolan/skills/sapiens-animacion"
))
if not _THEME_DIR.exists():
    _local = Path(r"c:\Users\USUARIO\Desktop\Proyectos\Animaciones")
    if _local.exists():
        _THEME_DIR = _local
sys.path.insert(0, str(_THEME_DIR))

# ── Resolver ruta a los templates ─────────────────────────────────────────────
_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from manim import Scene                    # noqa: E402

from animacion_templates import (          # noqa: E402
    BarChartTemplate,
    CurveRevealTemplate,
    StepRevealTemplate,
)

_TEMPLATES = {
    "BarChart":    BarChartTemplate,
    "CurveReveal": CurveRevealTemplate,
    "StepReveal":  StepRevealTemplate,
}


class SapiensAnimScene(Scene):
    """
    Escena genérica que carga anim_params.json y delega en el template correcto.
    La cámara se configura dentro de BaseTemplate._setup_scene().
    """

    def construct(self):
        params_path = os.environ.get("ANIM_PARAMS_PATH", "")
        if not params_path:
            raise RuntimeError("ANIM_PARAMS_PATH no definido")

        params = json.loads(Path(params_path).read_text(encoding="utf-8"))
        template_name = params.get("template", "BarChart")
        cls = _TEMPLATES.get(template_name)
        if cls is None:
            raise ValueError(
                f"Template desconocido: {template_name!r}. "
                f"Opciones: {list(_TEMPLATES)}"
            )
        cls(self, params).render()
