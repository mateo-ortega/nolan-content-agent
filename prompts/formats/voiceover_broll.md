# Formato: voiceover_broll

## Cuándo usar este formato

Narrativas emocionales o testimoniales cortas (15–30s) donde el valor está en el **arco de historia**, no en la lista de puntos. Mejor que un carrusel cuando hay un personaje, un antes y un después, o una situación concreta que el lector puede imaginar visualmente.

## Estructura narrativa (5 beats)

```
Beat 1 — GANCHO    (2–4s)  Situación de tensión o pregunta que atrapa
Beat 2 — CONTEXTO  (3–5s)  Por qué esta situación es más común de lo que parece
Beat 3 — GIRO      (4–7s)  El cambio, el método, la revelación
Beat 4 — RESULTADO (4–6s)  Qué pasó cuando aplicó eso (concreto, medible o visceral)
Beat 5 — CIERRE    (2–4s)  Micro-acción o insight que el lector puede usar hoy
```

## Script JSON output (copywriter → producción)

```json
{
  "beats": [
    {
      "id": 1,
      "role": "gancho",
      "voiceover": "Andrea llevaba cuatro semanas sin dormir bien antes del Saber 11.",
      "broll_keywords": ["student stressed", "notebook night", "colombia school"],
      "duration_s": 3.5
    },
    {
      "id": 2,
      "role": "contexto",
      "voiceover": "No era falta de estudio. Era que nadie le había enseñado a estudiar para este tipo de prueba.",
      "broll_keywords": ["study table books", "highlighter notes", "colombia student"],
      "duration_s": 5.0
    },
    ...
  ],
  "voiceover_params": {
    "language": "es-co-neutral",
    "style": "calm_conversational",
    "elevenlabs_stability": 0.40,
    "elevenlabs_similarity": 0.85
  },
  "total_duration_s": 24.5,
  "nicho": "jovenes_preicfes"
}
```

## Reglas de copy para voiceover

- Velocidad natural: 135–155 palabras por minuto en español conversacional. Calibrar `duration_s` acordemente.
- Primera oración: nombre/situación concreta, no abstracta. "Los estudiantes sienten que..." → peor. "Andrea llevaba cuatro semanas..." → mejor.
- Evitar: "Hoy te voy a contar...", "En este video...", "Bienvenido a...".
- Cero emojis. Cero hashtags en el guion.
- El voiceover va en primera persona narrativa de tercero si es testimonial, o directamente en segunda persona si es instruccional.

## Reglas de b-roll

- Keywords en inglés para Pexels/Pixabay (mayor cobertura).
- Priorizar: gente real en situaciones cotidianas > stock genérico de oficina brillante.
- Vertical-native (9:16) si existe; si no, crop 1080×1920 del centro del clip horizontal.
- Evitar: clips con texto en pantalla (chocan con subtítulos), logos de marcas visibles, clips con música propia audible.

## Subtítulos

- Fuente: Outfit Bold, 54pt, color blanco con stroke negro 4px.
- Keyword del beat en gold `#E8A838` — la palabra más cargada de cada oración.
- Máx 2 líneas simultáneas en pantalla.
- Timestamp de palabras vía `whisper.cpp` (español).
