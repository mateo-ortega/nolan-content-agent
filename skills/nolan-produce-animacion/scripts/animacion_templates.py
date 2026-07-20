"""
Templates Manim para Nolan — Sapiens by Shift.
Construidos sobre sapiens_theme.py (paleta, safe zones, logo, outro).

Sistema de coordenadas: frame_width=9, frame_height=16
  x ∈ [-4.5, 4.5], y ∈ [-8, 8]
  IG safe zone: x ∈ [-4.2, 3.5], y ∈ [-5.5, 6.6]
  Logo hero: y = -4.4  → contenido hasta y ≥ LOGO_SAFE_FLOOR (-4.4)

Templates disponibles:
  BarChart    — barras horizontales (comparaciones, rankings)
  CurveReveal — curvas sobre ejes (tendencias, decaimiento)
  StepReveal  — pasos secuenciales (métodos, procesos)

Principios de safe zone:
  - Todo texto se crea con font_size calculado para caber en _MAX_TEXT_W
    SIN usar set_width(), evitando el bug Write+scale de Manim.
  - _clamp_x() se aplica como red de seguridad final en cada elemento.
  - _MAX_TEXT_W = 6.5u (margen de 0.5u respecto al límite real de 7.0u).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Resolver ruta a sapiens_theme.py ─────────────────────────────────────────
_THEME_DIR = Path(os.environ.get(
    "SAPIENS_THEME_DIR",
    "/srv/sapiens-nolan/skills/sapiens-animacion"
))
if not _THEME_DIR.exists():
    _local = Path(r"c:\Users\USUARIO\Desktop\Proyectos\Animaciones")
    if _local.exists():
        _THEME_DIR = _local
sys.path.insert(0, str(_THEME_DIR))

from manim import *                        # noqa: E402, F401, F403
import numpy as np                         # noqa: E402

from sapiens_theme import (                # noqa: E402
    get_palette,
    REELS_WIDTH, REELS_HEIGHT,
    IG_SAFE_TOP, IG_SAFE_BOTTOM, IG_SAFE_LEFT, IG_SAFE_RIGHT,
    LOGO_SAFE_FLOOR, LOGO_HERO_Y,
    sapiens_background,
    sapiens_logo_hero, sapiens_logo_entrance, sapiens_logo_pulse,
    play_sapiens_outro,
    SapiensTitle, sapiens_rule,
)

_LOGO_PATH: str = os.environ.get(
    "SAPIENS_LOGO_PATH",
    str(_THEME_DIR / "sapiens_logo_wm.png"),
)

MODE: str = os.environ.get("SAPIENS_MODE", "dark")
P: dict   = get_palette(MODE)

_SURF_DARK  = "#1A1C22"
_SURF_LIGHT = "#F0EDE8"
SURF = _SURF_DARK if MODE == "dark" else _SURF_LIGHT

# Ancho máximo CONSERVADOR: 6.5u deja 0.5u de margen respecto al límite real
# de la safe zone (7.0u entre IG_SAFE_LEFT y IG_SAFE_RIGHT centrados en x=0).
# El margen absorbe anti-aliasing y cualquier imprecisión del renderer Manim.
_MAX_TEXT_W: float = 6.5

BRAND_COLORS = {
    "teal":   P["teal"],
    "gold":   P["gold"],
    "text":   P["text"],
    "dim":    P["text_secondary"],
    "red":    "#E85D5D",
    "violet": "#7C6DD8",
}


def _bc(name: str) -> str:
    return BRAND_COLORS.get(name, P["teal"])


# ── Helpers de safe zone ──────────────────────────────────────────────────────

def _fit_text(text: str, font: str, font_size: int, color: str,
              weight: str = NORMAL, line_spacing: float = 1.0,
              max_w: float = None) -> "Text":
    """
    Crea un objeto Text con font_size reducido proporcionalmente para que
    su ancho quepa en max_w (default _MAX_TEXT_W).

    IMPORTANTE: usa font_size nativo en lugar de set_width() para evitar
    el bug de Manim donde Write() sobre objetos escalados con set_width()
    produce paths de caracteres en coordenadas incorrectas.
    """
    limit = max_w if max_w is not None else _MAX_TEXT_W
    kwargs = dict(font=font, font_size=font_size, color=color, weight=weight)
    if line_spacing != 1.0:
        kwargs["line_spacing"] = line_spacing
    t = Text(text, **kwargs)
    if t.width > limit:
        new_size = max(int(font_size * limit / t.width), 14)
        kwargs["font_size"] = new_size
        t = Text(text, **kwargs)
    return t


def _clamp_x(mob, x_min: float = None, x_max: float = None):
    """Desplaza mob horizontalmente para que quede dentro del safe zone IG."""
    lo = x_min if x_min is not None else IG_SAFE_LEFT
    hi = x_max if x_max is not None else IG_SAFE_RIGHT
    left  = mob.get_left()[0]
    right = mob.get_right()[0]
    if left < lo:
        mob.shift(RIGHT * (lo - left))
    if right > hi:
        mob.shift(LEFT * (right - hi))
    return mob


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseTemplate:
    """
    Configura la cámara, añade fondo tech y logo, expone _hook() y _conclusion().
    Llamar _setup_scene() al inicio de render().
    """

    def __init__(self, scene: Scene, params: dict):
        self.s = scene
        self.p = params
        self._logo       = None
        self._logo_img   = None
        self._scene_objs: list = []

    def _setup_scene(self):
        self.s.camera.frame_width      = REELS_WIDTH
        self.s.camera.frame_height     = REELS_HEIGHT
        self.s.camera.background_color = P["bg"]

        bg = sapiens_background(P, with_grid=True, grid_style="dots", grid_opacity=0.12)
        self.s.add(*bg)

        self._logo     = sapiens_logo_hero(P, logo_path=_LOGO_PATH)
        self._logo_img = getattr(self._logo, "_logo_img", None)

    def _hook(self):
        lines = self.p.get("hook", "").strip().splitlines()
        sapiens_logo_entrance(self.s, self._logo, run_time=0.75)
        if not lines:
            return

        texts = []
        for i, line in enumerate(lines[:3]):
            if i == 1:
                color  = _bc(self.p.get("hook_accent_color", "teal"))
                size   = 66
                weight = BOLD
            else:
                color  = P["text"]
                size   = 54
                weight = NORMAL
            t = _fit_text(line.strip(), "Instrument Sans", size, color,
                          weight=weight)
            _clamp_x(t)
            texts.append(t)

        grp = VGroup(*texts).arrange(DOWN, buff=0.55).move_to(UP * 1.8)
        self.s.play(FadeIn(grp, shift=DOWN * 0.25), run_time=1.0)
        self.s.wait(1.5)
        self.s.play(FadeOut(grp, shift=UP * 0.4), run_time=0.50)

    def _conclusion(self):
        text = self.p.get("conclusion", "").strip()
        if not text:
            play_sapiens_outro(self.s)
            return

        lines = text.splitlines()
        objs  = []
        for i, line in enumerate(lines[:2]):
            color  = P["teal"] if i == 1 else P["text"]
            size   = 60 if i == 1 else 52
            t = _fit_text(line.strip(), "Instrument Sans", size, color,
                          weight=BOLD)
            _clamp_x(t)
            objs.append(t)

        grp = VGroup(*objs).arrange(DOWN, buff=0.55).move_to(UP * 0.8)
        sapiens_logo_pulse(self.s, self._logo)
        # FadeIn en lugar de Write para evitar el bug de paths incorrectos
        # en objetos cuyo font_size fue reducido por _fit_text.
        for obj in objs:
            self.s.play(FadeIn(obj, shift=UP * 0.12), run_time=0.75)
        self.s.wait(1.6)
        self.s.play(FadeOut(grp), run_time=0.55)

        play_sapiens_outro(self.s)

    def render(self):
        raise NotImplementedError


# ── Template 1: BarChart ──────────────────────────────────────────────────────

class BarChartTemplate(BaseTemplate):
    """
    Barras horizontales animadas (9×16).

    params.bars: [{label, value: 0-100, highlight: bool, color: str}]
    params.title: str  (subtítulo opcional)
    """

    def render(self):
        self._setup_scene()
        self._hook()

        bars_data = self.p.get("bars", [])
        title_txt = self.p.get("title", "")
        n = len(bars_data)
        if not n:
            self._conclusion()
            return

        title_obj = None
        if title_txt:
            title_obj = _fit_text(title_txt, "Instrument Sans", 32,
                                  P["text_secondary"], max_w=_MAX_TEXT_W)
            title_obj.move_to(UP * 3.8)
            _clamp_x(title_obj)
            self.s.play(FadeIn(title_obj), run_time=0.40)

        bar_h  = 0.65
        gap    = 0.42
        # max_w reducido a 4.6u: borde derecho en -1.35+4.6=3.25 ≤ IG_SAFE_RIGHT=3.5
        max_w  = 4.6
        x_orig = -1.35
        total_h = n * (bar_h + gap) - gap
        start_y = total_h / 2.0 - bar_h / 2.0

        rows = VGroup()
        for i, item in enumerate(bars_data):
            label     = item.get("label", "")
            pct       = float(item.get("value", 0))
            highlight = item.get("highlight", False)
            bar_color = _bc(item.get("color", "teal" if highlight else ""))
            if not highlight:
                bar_color = SURF

            y     = start_y - i * (bar_h + gap)
            bar_w = max_w * pct / 100.0

            # Label: clamp ANTES de posicionar para evitar que set_width
            # desplace el centro hacia la izquierda y saque el borde del frame.
            lbl = _fit_text(label, "Instrument Sans", 27, P["text"],
                            max_w=2.3)
            # Alinear borde DERECHO del label a x_orig - 0.14
            lbl.align_to(np.array([x_orig - 0.14, 0, 0]), RIGHT)
            lbl.set_y(y)
            _clamp_x(lbl, x_min=IG_SAFE_LEFT)

            bg = Rectangle(
                width=max_w, height=bar_h,
                fill_color=_SURF_DARK, fill_opacity=0.55, stroke_width=0,
            )
            bg.align_to(np.array([x_orig, 0, 0]), LEFT).set_y(y)

            bar = Rectangle(
                width=max(bar_w, 0.02), height=bar_h,
                fill_color=bar_color, fill_opacity=0.92, stroke_width=0,
            )
            bar.align_to(np.array([x_orig, 0, 0]), LEFT).set_y(y)

            pc_color = P["gold"] if highlight else P["text_secondary"]
            pc = _fit_text(f"{int(pct)}%", "Instrument Sans", 27, pc_color,
                           weight=BOLD if highlight else NORMAL, max_w=0.9)
            # Porcentaje dentro del fondo de la barra, borde derecho en x=3.25
            pc.next_to(np.array([x_orig + max_w - 0.12, y, 0]), LEFT, buff=0.0)
            _clamp_x(pc)

            self.s.play(
                FadeIn(lbl, run_time=0.16),
                FadeIn(bg,  run_time=0.16),
                GrowFromEdge(bar, LEFT, run_time=0.58),
                FadeIn(pc,  run_time=0.22),
            )
            rows.add(VGroup(lbl, bg, bar, pc))

        # Pulso en highlights
        self.s.wait(0.60)
        for row, item in zip(rows, bars_data):
            if item.get("highlight"):
                self.s.play(row.animate.scale(1.04), run_time=0.22)
                self.s.play(row.animate.scale(1 / 1.04), run_time=0.14)

        self.s.wait(0.45)
        to_out = [rows]
        if title_obj is not None:
            to_out.append(title_obj)
        self.s.play(FadeOut(Group(*to_out)), run_time=0.50)
        self._conclusion()


# ── Template 2: CurveReveal ───────────────────────────────────────────────────

class CurveRevealTemplate(BaseTemplate):
    """
    Una o dos curvas sobre ejes x/y (9×16).

    params.curves: [{label, color, type: "decay"|"growth"|"custom",
                     custom_points: [[x,y]...]}]
    params.x_label, y_label
    params.x_range [0,7,1], y_range [0,1.0,0.5]
    params.markers: [{x, curve_index}]
    """

    def render(self):
        self._setup_scene()
        self._hook()

        x_range = self.p.get("x_range", [0, 7, 1])
        y_range = self.p.get("y_range", [0, 1.0, 0.5])
        curves  = self.p.get("curves", [])

        axes = Axes(
            x_range=x_range,
            y_range=y_range,
            x_length=6.0,
            y_length=5.5,
            axis_config={"color": P["text_secondary"], "stroke_width": 1.6},
            tips=False,
        ).shift(DOWN * 0.25)

        # Etiquetas de ejes con _fit_text y clamp
        xl = _fit_text(self.p.get("x_label", ""), "Instrument Sans", 26,
                       P["text_secondary"], max_w=2.0)
        xl.next_to(axes.x_axis.get_end(), RIGHT, buff=0.10)
        _clamp_x(xl)

        yl = _fit_text(self.p.get("y_label", ""), "Instrument Sans", 26,
                       P["text_secondary"], max_w=2.0)
        yl.rotate(90 * DEGREES)
        yl.next_to(axes.y_axis.get_top(), UP, buff=0.10)

        self.s.play(Create(axes), FadeIn(xl), FadeIn(yl), run_time=0.95)

        def _build_fn(c_def: dict):
            ctype = c_def.get("type", "decay")
            if ctype == "decay":
                return lambda t: 0.92 * np.exp(-0.38 * t) + 0.08
            if ctype == "growth":
                return lambda t: 1 - 0.9 * np.exp(-0.4 * t)
            if ctype == "custom":
                pts = c_def.get("custom_points", [[0, 0], [7, 0.5]])
                xs  = [p[0] for p in pts]
                ys  = [p[1] for p in pts]
                return lambda t: float(np.interp(t, xs, ys))
            return lambda t: 0.5

        plotted: list[tuple] = []
        labels_added: list   = []
        for c_def in curves:
            color = _bc(c_def.get("color", "teal"))
            label = c_def.get("label", "")
            x0, x1 = float(x_range[0]), float(x_range[1])
            fn    = _build_fn(c_def)
            curve = axes.plot(fn, x_range=[x0, x1], color=color, stroke_width=3.5)
            self.s.play(Create(curve), run_time=1.75)
            if label:
                lbl = _fit_text(label, "Instrument Sans", 26, color, max_w=2.5)
                lbl.next_to(curve.get_end(), DOWN + RIGHT * 0.10, buff=0.12)
                _clamp_x(lbl)
                self.s.play(FadeIn(lbl), run_time=0.35)
                labels_added.append(lbl)
            plotted.append((fn, curve))

        for mkr in self.p.get("markers", []):
            mx  = float(mkr["x"])
            idx = mkr.get("curve_index", 0)
            if idx < len(plotted):
                fn, _ = plotted[idx]
                my   = fn(mx)
                dot  = Dot(axes.c2p(mx, my), color=P["gold"], radius=0.14)
                tick = DashedLine(
                    axes.c2p(mx, 0), axes.c2p(mx, my),
                    color=P["gold"], stroke_width=1.6, dash_length=0.08,
                )
                self.s.play(FadeIn(tick), FadeIn(dot, scale=2.0), run_time=0.30)

        self.s.wait(0.70)
        all_content = Group(axes, xl, yl,
                            *[c for _, c in plotted],
                            *labels_added)
        self.s.play(FadeOut(all_content), run_time=0.55)
        self._conclusion()


# ── Template 3: StepReveal ────────────────────────────────────────────────────

class StepRevealTemplate(BaseTemplate):
    """
    Lista de pasos numerados que aparecen uno a uno (9×16).

    params.steps: [{number, text, color}]
    params.title: str
    """

    def render(self):
        self._setup_scene()
        self._hook()

        title_txt = self.p.get("title", "")
        steps     = self.p.get("steps", [])
        n         = len(steps)
        if not n:
            self._conclusion()
            return

        title_obj = None
        if title_txt:
            title_obj = _fit_text(title_txt, "Instrument Sans", 34,
                                  P["text_secondary"], max_w=_MAX_TEXT_W)
            title_obj.move_to(UP * 3.8)
            _clamp_x(title_obj)
            self.s.play(FadeIn(title_obj), run_time=0.38)

        step_h  = 1.0
        gap     = 0.45
        total_h = n * step_h + (n - 1) * gap
        start_y = total_h / 2.0 - step_h / 2.0

        # Ancho disponible para el texto: desde right(num_circle) hasta IG_SAFE_RIGHT
        # num_circle.center=-2.5, radius=0.40, right=-2.1, buff=0.30 → text_left=-1.80
        # text_max_w = IG_SAFE_RIGHT - text_left - margen = 3.5 - (-1.80) - 0.15 = 5.15
        STEP_TEXT_MAX_W = 5.0

        step_objs = VGroup()
        for i, step in enumerate(steps):
            y     = start_y - i * (step_h + gap)
            color = _bc(step.get("color", "teal"))
            num   = step.get("number", str(i + 1))
            text  = step.get("text", "")

            num_circle = Circle(radius=0.40, color=color,
                                fill_opacity=0.18, stroke_width=2.2)
            num_txt    = _fit_text(str(num), "Instrument Sans", 30, color,
                                   weight=BOLD, max_w=0.5)
            num_circle.move_to([-2.5, y, 0])
            num_txt.move_to(num_circle.get_center())

            # set_width + next_to solo si se hace en este orden:
            # primero _fit_text (limita font_size), luego next_to (posiciona).
            step_txt = _fit_text(text, "Instrument Sans", 32, P["text"],
                                 max_w=STEP_TEXT_MAX_W)
            step_txt.next_to(num_circle, RIGHT, buff=0.30)
            _clamp_x(step_txt)

            self.s.play(
                FadeIn(num_circle, scale=0.7, run_time=0.28),
                FadeIn(num_txt,    run_time=0.22),
                FadeIn(step_txt,   shift=RIGHT * 0.15, run_time=0.42),
            )
            step_objs.add(VGroup(num_circle, num_txt, step_txt))

        self.s.wait(0.75)
        to_out = [step_objs]
        if title_obj is not None:
            to_out.append(title_obj)
        self.s.play(FadeOut(Group(*to_out)), run_time=0.52)
        self._conclusion()
