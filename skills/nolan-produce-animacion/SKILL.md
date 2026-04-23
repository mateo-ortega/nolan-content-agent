---
name: nolan-produce-animacion
description: Adapter que toma un brief con format=animacion y produce un MP4 Manim 1080x1920 invocando la skill legacy sapiens-animacion (Manim + LaTeX). Genera guion de escena, llama render Manim, muxea voiceover opcional, escribe caption. Reservado para temas matemáticos/físicos/químicos con transformación visual.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [production, animacion, manim, sapiens, nolan]
    category: sapiens
    requires_toolsets: [terminal, llm]
---

# nolan-produce-animacion

Wrapper sobre `sapiens-animacion` (Manim Community + LuaLaTeX + `sapiens_theme.py`). Genera MP4 vertical 1080×1920 60fps para Reels con identidad Sapiens (teal/gold/dark).

## When to use

Brief recibido de `nolan-decide-format` con `format: animacion`. Reservado a 1–2 piezas/semana por costo de render.

## Procedure

1. **Cargar brief** + `memory/brand_context.md` + `SOUL.md` + `prompts/formats/animacion.md`.
2. **Generar guion de escena** vía `copy.animacion_scene_script` (Claude Sonnet 4.6, cached):
   - Entrada: brief (thesis + pillars + fórmula LaTeX si aplica).
   - Salida: Python Manim class con estructura `SAPIENS_<slug>_v<N>.py` que hereda tema; duración objetivo 15–30s; voiceover caption opcional.
3. **Validar sintaxis Python** (`py -3.12 -m py_compile`). Si falla, reintentar una vez con error como contexto.
4. **Chequeo ethics** sobre texto on-screen + caption.
5. **Persistir** `staging/<piece_id>/scene.py`.
6. **Invocar render**:
   ```bash
   cd /srv/sapiens-nolan/skills/sapiens-animacion && \
   py -3.12 -m manim -qh -r 1080,1920 --fps 60 \
       "/srv/sapiens-nolan/staging/<piece_id>/scene.py" \
       "<ClassName>" \
       -o "piece.mp4" \
       --media_dir "/srv/sapiens-nolan/staging/<piece_id>/media"
   ```
7. **(Opcional) voiceover**: si brief pide narración, generar vía ElevenLabs (`production.voiceover`) y muxear con ffmpeg.
8. **Extraer cover.jpg** del frame más representativo (default: segundo 1).
9. **Generar preview.mp4** 480p para Telegram.
10. **Generar caption** vía `copy.final_caption`.
11. **Escribir metadata.json** (incluye `render_seconds`, `manim_quality`).

## Brand lock

- Fondo: dark (`#0B0D12`) por default en animaciones — es la excepción a light-mode.
- Fórmulas LaTeX: `lualatex` con `sapiens_tex_template` (fuentes Outfit/Jura embebidas).
- Fallback: `sapiens_tex_template_compat` con `pdflatex` sin fontspec si lualatex falla en el VPS.
- Logo wordmark inferior derecho último segundo (últimos 2s).
- Colores ecuaciones: gold `#E8A838` en término clave, teal `#2B9E8F` en resultado, blanco resto.

## Pitfalls

- **LuaLaTeX roto**: si `lualatex --version` falla o template da error, activar `SAPIENS_TEX_TEMPLATE=compat` y reintentar. No intentar render sin LaTeX; abortar.
- **Render timeout**: render 1080p 60fps ≈ 4–6 GB RAM y 3–8 min. Si falla por OOM, bajar a `-qm` (720p) y flag en metadata.
- **Manim reuses cache**: borrar `media/Tex/` y `media/texts/` si cambian fuentes. Cron de limpieza semanal.
- **Voice-text desync**: si se genera voiceover, validar que `len(voiceover_seconds) ≈ sum(scene.durations)` ±0.5s. Si no, reintentar guion pidiendo ajuste.

## Verification

```bash
hermes chat "produce_animacion --brief staging/fixtures/brief-binomio-cuadrado.yaml --dry-run"
# Esperado: staging/<piece_id>/piece.mp4 (1080x1920, ~20s, <15 MB)
ffprobe staging/.../piece.mp4 2>&1 | grep -E "1080x1920|Duration"
```

## Outputs

```
staging/<piece_id>/
├── scene.py
├── piece.mp4               (1080x1920 60fps)
├── preview.mp4             (480x854, para Telegram)
├── cover.jpg
├── caption.md
├── metadata.json
├── alt_text.md
└── sources.md
```
