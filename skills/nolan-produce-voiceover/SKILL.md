---
name: nolan-produce-voiceover
description: Produce un Reel vertical 1080x1920 combinando b-roll de stock (Pexels/Pixabay) con voiceover sintético (ElevenLabs opcional) + subtítulos quemados + música ducking. Reservado para narrativas emocionales cortas (15-30s) y testimoniales L1.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [production, voiceover, broll, reel, sapiens, nolan]
    category: sapiens
    requires_toolsets: [terminal, llm, http]
---

# nolan-produce-voiceover

Pipeline ffmpeg: descarga b-roll libre → genera voiceover → muxea audio+video → quema subtítulos → añade música de fondo con ducking → output MP4 Reel.

## When to use

Brief recibido de `nolan-decide-format` con `format: voiceover_broll`. Default para arcos narrativos cortos (`caso de`, `historia de`, `cómo pasó X a Y`).

## Procedure

1. **Cargar brief** + `memory/brand_context.md` + `prompts/formats/voiceover_broll.md`.
2. **Generar guion voiceover** (`copy.voiceover_script`, Claude Sonnet cached):
   - Estructura: 3–5 beats (gancho / desarrollo / giro / payoff / cta).
   - Duración objetivo 20–28s (calibrado a 135–160 wpm en español neutro).
   - Output: JSON `{beats:[{text, broll_keywords, duration_s}], voiceover_params}`.
3. **Chequeo ethics** sobre script completo.
4. **Descargar b-roll**:
   - Prefetch ordenado: `pexels_api` → `pixabay_api` (libres sin attribution obligatoria).
   - Por beat: 2–3 clips candidatos, elegir el que case `broll_keywords` + vertical-friendly.
   - Crop a 1080×1920 (reframe inteligente con ffmpeg `cropdetect` + `scale,pad`).
5. **Generar voiceover**:
   - Si `ELEVENLABS_API_KEY` presente → `eleven_multilingual_v2` voz pre-aprobada.
   - Fallback: dejar `voiceover.mp3` vacío + flag `needs_human_vo: true` en metadata (Mateo graba).
6. **Generar subtítulos**:
   - `whisper.cpp` transcribe voiceover (timestamps palabra).
   - Render SRT con plantilla Sapiens (Outfit Bold 54pt, stroke negro 4px, ghost gold en keywords).
7. **Ensamblar con ffmpeg**:
   ```bash
   ffmpeg -i broll_concat.mp4 -i voiceover.mp3 -i music_bg.mp3 \
     -filter_complex "[2:a]volume=0.15,sidechaincompress=threshold=0.1[music_duck]; \
                      [1:a][music_duck]amix=inputs=2[aout]" \
     -map 0:v -map "[aout]" -vf "subtitles=subs.srt:force_style='...'" \
     -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k -r 30 \
     piece.mp4
   ```
8. **Generar caption + alt_text + cover** (frame a los 2s).
9. **Escribir metadata.json** con lista de `broll_attributions[]` (aunque sea licencia libre, trazabilidad).

## Brand lock

- Música: de biblioteca propia `shared/music/` (pre-curada sin copyright). Nunca YouTube Audio Library de terceros.
- Subtítulos: ghost teal `#2B9E8F` en palabras de acción, gold `#E8A838` en la frase hero.
- Transiciones: cut duro. Sin fades marketing-y ni zoom-in agresivos.
- Voz: cadencia calmada, tuteo colombiano neutro. No locución radial.

## Pitfalls

- **B-roll pobre**: Pexels devuelve mucho lifestyle genérico. Si la keyword es muy específica (ej. `lectura crítica`), aceptar clips laterales (biblioteca, estudiante escribiendo) sin forzar literal.
- **Voiceover robótico**: ElevenLabs tiende a ser plano en español; ajustar `stability: 0.4, similarity: 0.85, style: 0.2` y pedir al script frases cortas.
- **Sync voiceover/subs**: whisper.cpp en español tiene word-timestamps ±80ms. Aceptable; si es mucho, usar WhisperX forzado.
- **Attribution requirements**: validar licencia por clip. Pixabay permite uso comercial sin crédito; Pexels igual. Guardar URL original en metadata.

## Verification

```bash
hermes chat "produce_voiceover --brief staging/fixtures/brief-testimonial-ana.yaml --dry-run"
# Esperado: piece.mp4 ~25s, 1080x1920, audio mixdown coherente, SRT quemado
ffprobe -v error -show_entries format=duration staging/.../piece.mp4
```

## Outputs

```
staging/<piece_id>/
├── piece.mp4                 (1080x1920 30fps, 15-30s)
├── preview.mp4               (480p para Telegram)
├── voiceover.mp3
├── subs.srt
├── broll_manifest.json       (URLs + licencias)
├── script.md                 (por si Mateo quiere re-grabar)
├── cover.jpg
├── caption.md
├── alt_text.md
└── metadata.json
```
