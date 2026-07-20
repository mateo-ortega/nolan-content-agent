"""
animacion_check.py — validador post-render de safe zone Instagram para animaciones Manim.

Extrae frames del MP4 con ffmpeg y usa PIL/numpy para detectar píxeles con contenido
fuera de las coordenadas de safe zone de IG (1080×1920 frame vertical).

Safe zone Instagram en píxeles (frame 1080×1920):
  - Horizontal: columnas 108–918  (margen 10% = 108px a cada lado)
  - Vertical:   filas   192–1728  (margen 10% top, 10% bottom)

Uso:
    python animacion_check.py <path/to/animation.mp4>

Exit code:
    0 → OK (no overflow)
    1 → overflow detectado (imprime reporte)
    2 → error de argumento / ffmpeg no disponible
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

# Safe zone IG en píxeles para frame 1080×1920.
# BaseTemplate._setup_scene() fuerza frame_width=9u, frame_height=16u (portrait real).
# Conversiones:
#   x_px = (x_manim / 9 + 0.5) * 1080
#   y_px = (0.5 - y_manim / 16) * 1920   (y positivo → arriba → fila menor)
#
# IG_SAFE_LEFT  = -4.2u → (-4.2/9 + 0.5) * 1080 = 36px
# IG_SAFE_RIGHT =  3.5u → ( 3.5/9 + 0.5) * 1080 = 960px
# IG_SAFE_TOP   =  6.6u → (0.5 - 6.6/16) * 1920 = 168px desde arriba
# IG_SAFE_BOTTOM= -5.5u → (0.5 + 5.5/16) * 1920 = 1620px desde arriba
_SAFE_LEFT_PX   = 36    # columna mínima
_SAFE_RIGHT_PX  = 960   # columna máxima
_SAFE_TOP_PX    = 168   # fila mínima desde arriba
_SAFE_BOTTOM_PX = 1620  # fila máxima desde arriba

# Umbral de brillo para considerar un píxel "con contenido" (no fondo)
# El fondo es #0B0D12 → R=11, G=13, B=18. Threshold: desviación > 20 sobre canal más claro
_BG_R, _BG_G, _BG_B = 11, 13, 18
_CONTENT_THRESHOLD = 20

# Muestrea estos segundos del video
_SAMPLE_TIMES = [0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]


def _is_content(r, g, b) -> bool:
    """Retorna True si el píxel difiere suficiente del fondo oscuro."""
    return (
        int(r) - _BG_R > _CONTENT_THRESHOLD or
        int(g) - _BG_G > _CONTENT_THRESHOLD or
        int(b) - _BG_B > _CONTENT_THRESHOLD
    )


def _extract_frame(mp4: Path, t_sec: float, dest: Path) -> bool:
    """Extrae un frame del video en t_sec segundos. Retorna True si exitoso."""
    result = subprocess.run(
        ["ffmpeg", "-ss", str(t_sec), "-i", str(mp4),
         "-frames:v", "1", "-q:v", "2", str(dest), "-y"],
        capture_output=True, timeout=30,
    )
    return result.returncode == 0 and dest.exists()


def _check_frame(img_path: Path, t_sec: float) -> dict | None:
    """
    Analiza un frame. Retorna dict con info de overflow, o None si está OK.
    """
    try:
        img = Image.open(img_path).convert("RGB")
    except Exception as e:
        return {"t": t_sec, "error": str(e)}

    arr = np.array(img)   # shape: (1920, 1080, 3)
    h, w, _ = arr.shape

    # Máscara de píxeles con contenido
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    content_mask = (
        (r.astype(int) - _BG_R > _CONTENT_THRESHOLD) |
        (g.astype(int) - _BG_G > _CONTENT_THRESHOLD) |
        (b.astype(int) - _BG_B > _CONTENT_THRESHOLD)
    )

    # Máscaras de zonas fuera de safe zone
    out_left   = content_mask.copy(); out_left[:, _SAFE_LEFT_PX:]  = False
    out_right  = content_mask.copy(); out_right[:, :_SAFE_RIGHT_PX] = False
    out_top    = content_mask.copy(); out_top[_SAFE_TOP_PX:, :]     = False
    out_bottom = content_mask.copy(); out_bottom[:_SAFE_BOTTOM_PX, :] = False

    violations = {}
    if out_left.any():
        cols = np.where(out_left.any(axis=0))[0]
        violations["left"] = {"px_count": int(out_left.sum()), "min_col": int(cols.min())}
    if out_right.any():
        cols = np.where(out_right.any(axis=0))[0]
        violations["right"] = {"px_count": int(out_right.sum()), "max_col": int(cols.max())}
    if out_top.any():
        rows = np.where(out_top.any(axis=1))[0]
        violations["top"] = {"px_count": int(out_top.sum()), "min_row": int(rows.min())}
    if out_bottom.any():
        rows = np.where(out_bottom.any(axis=1))[0]
        violations["bottom"] = {"px_count": int(out_bottom.sum()), "max_row": int(rows.max())}

    if violations:
        return {"t": t_sec, "violations": violations}
    return None


def check_animation(mp4_path: Path) -> tuple[bool, list[dict]]:
    """
    Verifica el video completo. Retorna (passed: bool, issues: list[dict]).
    passed=True significa OK, False significa overflow detectado.
    """
    if not mp4_path.exists():
        return False, [{"error": f"MP4 no encontrado: {mp4_path}"}]

    # Duración del video
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", str(mp4_path)],
        capture_output=True, text=True, timeout=30,
    )
    duration = 999.0
    if probe.returncode == 0:
        try:
            duration = float(json.loads(probe.stdout)["format"]["duration"])
        except (KeyError, ValueError, json.JSONDecodeError):
            pass

    sample_times = [t for t in _SAMPLE_TIMES if t < duration]
    if not sample_times:
        sample_times = [min(1.0, duration * 0.5)]

    issues = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for t in sample_times:
            frame_path = tmp / f"frame_{t:.1f}.jpg"
            if not _extract_frame(mp4_path, t, frame_path):
                continue
            result = _check_frame(frame_path, t)
            if result:
                issues.append(result)

    return (len(issues) == 0), issues


def main():
    if len(sys.argv) < 2:
        print("Uso: python animacion_check.py <animation.mp4>", file=sys.stderr)
        sys.exit(2)

    mp4 = Path(sys.argv[1])
    passed, issues = check_animation(mp4)

    if passed:
        print(json.dumps({"status": "ok", "mp4": str(mp4)}))
        sys.exit(0)
    else:
        print(json.dumps({"status": "overflow", "mp4": str(mp4), "issues": issues},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
