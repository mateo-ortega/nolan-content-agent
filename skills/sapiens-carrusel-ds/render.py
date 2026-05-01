"""
Sapiens Carrusel DS — render.py v1
Renderiza N slides HTML autosuficientes a PNGs 1080x1350 usando Playwright.

A diferencia del render.py de sapiens-carrusel (que usa Jinja2 + content.yaml),
este script asume que los HTMLs ya existen en piece_dir/slides/slide-*.html
(escritos por produce_carrusel_ds.py a partir del output del LLM).

Uso:
    py -3.12 render.py <piece_dir>

Donde piece_dir contiene:
    slides/slide-01.html ... slide-NN.html  (input)
    colors_and_type.css                     (referenciado por los HTMLs)
    fonts/                                  (referenciado por el CSS)
    assets/                                 (logos referenciados por los HTMLs)

Salida: piece_dir/slide-01.png ... slide-NN.png (al nivel del piece, no en slides/).
"""

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright


def main(piece_dir: str) -> int:
    piece = Path(piece_dir).resolve()
    slides_dir = piece / "slides"

    if not slides_dir.is_dir():
        print(f"[render-ds] ERROR: no existe {slides_dir}", file=sys.stderr)
        return 1

    html_files = sorted(slides_dir.glob("slide-*.html"))
    if not html_files:
        print(f"[render-ds] ERROR: no hay slide-*.html en {slides_dir}", file=sys.stderr)
        return 1

    css = piece / "colors_and_type.css"
    if not css.exists():
        print(f"[render-ds] WARN: {css} no existe — fuentes/tokens pueden romperse", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1080, "height": 1350},
            device_scale_factor=2,
        )

        for idx, html_path in enumerate(html_files, start=1):
            out_png = piece / f"slide-{idx:02d}.png"

            page.goto(html_path.as_uri())
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(400)

            # Safe-zone check: cualquier elemento con texto cuyo bounding rect
            # exceda 1080x1350 es un warning. Tolerancia 2px para sub-pixel.
            # Ignora .slide (es el canvas) y elementos de gradiente puro.
            violations = page.evaluate("""() => {
                const W = 1080, H = 1350, TOL = 2;
                const issues = [];
                const SKIP = new Set(['slide']);
                const text_tags = new Set(['H1','H2','H3','H4','P','SPAN','DIV','STRONG','EM','B','I']);
                document.querySelectorAll('*').forEach(el => {
                    if (!text_tags.has(el.tagName)) return;
                    if (!el.textContent.trim()) return;
                    const cls = el.className || '';
                    if (typeof cls === 'string') {
                        for (const skip of SKIP) {
                            if (cls.split(/\\s+/).includes(skip)) return;
                        }
                    }
                    const r = el.getBoundingClientRect();
                    if (r.width < 1 || r.height < 1) return;
                    const out = [];
                    if (r.right  > W + TOL) out.push('right=+'  + Math.round(r.right - W)  + 'px');
                    if (r.bottom > H + TOL) out.push('bottom=+' + Math.round(r.bottom - H) + 'px');
                    if (r.left   < -TOL)    out.push('left=-'   + Math.round(-r.left)      + 'px');
                    if (r.top    < -TOL)    out.push('top=-'    + Math.round(-r.top)       + 'px');
                    if (out.length === 0) return;
                    // Solo el contenedor más profundo
                    let isDeepest = true;
                    el.querySelectorAll('*').forEach(child => {
                        if (text_tags.has(child.tagName) && child.textContent.trim()) {
                            const cr = child.getBoundingClientRect();
                            if (cr.right > W + TOL || cr.bottom > H + TOL ||
                                cr.left < -TOL || cr.top < -TOL) isDeepest = false;
                        }
                    });
                    if (!isDeepest) return;
                    const label = (cls && typeof cls === 'string')
                        ? cls.split(/\\s+/)[0] || el.tagName
                        : el.tagName;
                    const preview = el.textContent.trim().slice(0, 40);
                    issues.push(label + ' [' + out.join(', ') + '] "' + preview + '"');
                });
                return issues;
            }""")

            status = "OK"
            if violations:
                status = "WARN"
                for v in violations:
                    print(f"    [safe-zone] slide-{idx:02d}: {v}", file=sys.stderr)

            page.screenshot(
                path=str(out_png),
                omit_background=False,
                clip={"x": 0, "y": 0, "width": 1080, "height": 1350},
            )

            print(f"  [{idx:02d}/{len(html_files)}] {html_path.name} -> {out_png.name}  [{status}]")

        browser.close()

    print(f"\n[OK] {len(html_files)} slides renderizados en {piece}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: py -3.12 render.py <piece_dir>")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
