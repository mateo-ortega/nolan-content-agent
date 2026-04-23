# Formato: carrusel

## Estructura de un carrusel Sapiens

Un carrusel es una secuencia de slides que construye un argumento. No es una lista de puntos sueltos — es un arco. El lector debe sentir que avanzó en su comprensión entre el slide 1 y el último.

### Anatomía estándar (7 slides — adaptar según contenido)

| # | Rol del slide | Qué contiene |
|---|---|---|
| 1 | **Cover / gancho** | Título corto (≤10 palabras) + subtítulo opcional (≤15 palabras). La imagen más fuerte. |
| 2 | **Tesis / contexto** | La afirmación central o el problema que el carrusel resuelve. 1–3 oraciones. |
| 3–6 | **Desarrollo / pillars** | Un pilar por slide. Cada uno: punto concreto + evidencia o ejemplo. Máx 220 chars. |
| N-1 | **Síntesis / cierre** | La idea central resumida en 1 oración potente. O la micro-acción concreta. |
| N | **CTA / firma** | Wordmark `sapiens` + handle `@sapiens.ed` + CTA suave (guardar, compartir, preguntar). |

### Reglas de texto por slide

- `text`: máx 220 caracteres. Oración completa, no bullet truncado.
- `word`: 1 palabra del `text` que va en gold `#E8A838`. La más cargada semánticamente.
- Cero emojis en ningún slide.
- Cover: si hay un número en el título ("3 pasos", "7 señales"), ese número suele ser la `word`.

### Arquetipos y su estructura específica

**`senales`** (lista de señales, errores, síntomas):
- Cover: "N señales de que X" o "N errores que cometen los que Y"
- Pillar 2: contexto de por qué estas señales importan
- Pillars 3–N-1: una señal por slide, con descripción y por qué ocurre
- Cierre: qué hacer si reconoció varias señales

**`framework`** (pasos ejecutables):
- Cover: "El método de N pasos para X"
- Pillar 2: el problema que el método resuelve (por qué los métodos anteriores fallan)
- Pillars 3–N-1: un paso por slide, con instrucción concreta y qué resultado da
- Cierre: cómo empezar hoy (acción mínima viable)

**`tesis`** (una idea desarrollada en profundidad):
- Cover: la tesis contraintuitiva en pocas palabras
- Pillar 2: el mundo antes de entender la tesis (creencia común que va a desmontar)
- Pillars 3–N-1: los argumentos y evidencias que la sostienen
- Cierre: la implicación práctica de aceptar la tesis

**`comparativa`** (A vs B, mito vs realidad, antes vs después):
- Cover: el contraste en ≤8 palabras
- Pillar 2: por qué este contraste importa
- Pillars 3–N-1: cada dimensión de comparación en un slide (un lado del contraste por slide, o un par por slide según longitud)
- Cierre: cuándo usar A, cuándo B

**`ad_hoc`**: estructura libre — usarlo solo cuando el contenido genuinamente no encaja en los anteriores. Documentar en `brief.format_override_reason`.

## YAML de output (estructura para render.py de sapiens-carrusel)

```yaml
title: 'Título del carrusel'
subtitle: 'Subtítulo opcional'
color_scheme: light           # light (default) | dark
accent_color: '#E8A838'       # siempre gold — no cambiar
font_display: Outfit
font_body: Instrument Sans
slides:
  - id: 1
    layout: cover
    text: 'Texto del título'
    word: 'palabra'           # contenida verbatim en text
    subtext: 'Subtítulo'      # opcional, solo en covers
  - id: 2
    layout: body
    text: 'Texto del slide. Máx 220 caracteres por favor respetar.'
    word: 'palabra'
  # ... repetir para cada slide
  - id: N
    layout: cta
    text: 'sapiens'
    subtext: '@sapiens.ed'
    cta: 'Guardá esto para cuando lo necesites.'
```

**Restricción crítica**: todas las strings entre comillas simples ASCII `'`. Nunca `"` ni tipográficas.
