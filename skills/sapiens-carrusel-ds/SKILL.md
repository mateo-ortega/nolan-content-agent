---
name: sapiens-carrusel-ds
version: 1.0.0
description: Sistema de diseño visual estructurado para carruseles 1080×1350 de Sapiens. Provee 7 plantillas HTML autosuficientes (Cover, Thesis, Comparative, Process, BigQuote, Stat, CTA), tokens CSS, fuentes (Outfit, Instrument Sans, Geist Mono, Jura) y logos. Alternativa al skill `sapiens-carrusel` (gestos tipográficos) — el copy se edita encima de los templates respetando la voz v2 del SOUL.
platforms: [linux]
metadata:
  hermes:
    tags: [design, carrusel, sapiens, design-system]
    category: sapiens
---

# sapiens-carrusel-ds — Sistema de diseño estructurado

Skill visual de carruseles tipo "magazine layout" para Sapiens. Complementa al skill `sapiens-carrusel` (gestos tipográficos dramáticos) ofreciendo otra estética: layouts estructurados con cards, comparativas, datos destacados, citas y procesos numerados. La rotación entre ambas skills da variedad al feed de @sapiens.ed.

> **Importante:** este skill SOLO ofrece el sistema visual. La voz, las prohibiciones de marca y las reglas editoriales están en [SOUL.md](../../SOUL.md). Si hay conflicto entre cualquier cosa escrita acá y el SOUL, **el SOUL gana**.

---

## When to use

Cuando el formato del día es `carrusel-ds` (jueves por defecto, ver `scripts/ciclo.sh`). El orquestador es `nolan-produce-carrusel-ds/scripts/produce_carrusel_ds.py`.

---

## Voz v2 — referencia obligatoria

El SOUL.md vigente define la voz: **autoridad técnica + calidez**. Mateo es ingeniero químico UNAL que diagnostica antes de prescribir, no un compañero peer-to-peer.

Reglas duras heredadas del SOUL que TODO copy de este skill debe cumplir:

- **Tagline:** `tu ruta. diseñada con método.` — nunca `aprende a tu medida` (deprecada).
- **Tuteo con respeto:** "tú", "tu hijo", nunca "usted".
- **Tutor experto, no compañero:** Mateo respeta al lector pero diagnostica con criterio. Cero "exploremos juntos", "construyamos", "compañero de viaje".
- **IA nunca es protagonista:** el sujeto activo de las frases es siempre el humano (estudiante, tutor, padre), nunca el modelo. Prohibido "par que razona", "colaborador", "agente que decide".
- **Vocabulario sapiens v2:** `diagnosticar, ruta, método, evidencia, datos, progreso, entender, claridad, práctica, caso, proceso, personalizado, resultado, prerequisito`.
- **Sin emojis** en los slides (excepción: nada — cero emojis aquí, a diferencia del SKILL.md original v1).
- **Sentence case** en títulos y body. Proper nouns retienen casing (`ICFES`, `UNAL`, `UdeA`).
- **Audiencia segments NUNCA en superficies públicas:** cero `L1`, `L2`, `Para padres`, `adultos_ia`. Eso es metadata interna.

---

## File inventory

```
SKILL.md                         — este archivo
colors_and_type.css              — tokens design + @font-face + utilidades

fonts/
  Outfit-VariableFont_wght.ttf       display, headings, hero
  InstrumentSans-VariableFont.ttf    body, UI
  GeistMono-VariableFont_wght.ttf    números, IDs, índices `01 / 07`
  Jura-VariableFont_wght.ttf         labels uppercase, eyebrows

assets/
  sapiens_logo.png                   horizontal master
  sapiens_logo_compact.png           compact icon + wordmark
  sapiens_logo_compact_white.png     compact white (sobre teal/dark)
  sapiens_icon_teal.svg              icon solo, teal
  sapiens_icon_white.svg             icon solo, white

slides/                              — 7 templates canónicos (copy + edit)
  Cover.html        portada teal con hero word
  Thesis.html       tesis con kicker + body
  Comparative.html  dos columnas (modelo viejo vs sapiens)
  Process.html      4 pasos numerados con paso activo en teal
  BigQuote.html     cita grande con atribución (cremoso)
  Stat.html         dato grande (380px) sobre teal-deep + fuente
  CTA.html          near-black con botón gold + tagline
```

---

## Cómo se usa el skill

El skill no se ejecuta solo. `produce_carrusel_ds.py` lo orquesta en este flujo:

1. Carga el brief + los 7 templates HTML como contexto.
2. Pide al LLM (Claude Sonnet, cached) que escoja 5-9 templates en orden narrativo y edite SOLO el contenido textual, devolviendo HTMLs separados por `<!--SLIDE_BREAK-->`.
3. Valida el output (CSS classes intactas, footer index correcto, voz v2, ethics gate).
4. Copia `colors_and_type.css`, `fonts/`, `assets/` al directorio del piece.
5. Escribe `slides/slide-NN.html` y luego invoca `render.py` para generar `slide-NN.png` 1080×1350.

---

## Reglas duras del sistema visual (no se relajan jamás)

- [ ] Wordmark **siempre lowercase** `sapiens` — nunca `Sapiens` o `SAPIENS`.
- [ ] Color primario **Sapiens Teal `#2B9E8F`** — nunca coral, nunca amber (esos son del parent brand Shift).
- [ ] Light mode siempre. Dark mode (CTA `#1A1C23`, Stat `#1E7A6D`) solo cuando el template lo define.
- [ ] Gold `#E8A838` o `#F5C542` solo para emphasis de UNA palabra o achievement — nunca background grande.
- [ ] Card radius default **14px** (más suave que el parent brand Shift).
- [ ] Fuentes self-hosted via `colors_and_type.css` — nunca Google Fonts CDN.
- [ ] Slides **1080×1350** exactos.
- [ ] Footer index `NN / NN` consistente con el total real de slides.

---

## Tipos de slide y cuándo usar cada uno

| Tipo | Background | Uso típico | Reglas de copy |
|---|---|---|---|
| **Cover** | teal `#2B9E8F` | Slide 01 — hero con palabra-concepto | Hero ≤ 4 palabras, eyebrow `sapiens · ed`, una palabra en gold opcional |
| **Thesis** | warm white `#FAFAF7` | Slide 02 — la pregunta o tesis | Tag `La tesis · 02 / NN`, kicker corto, thesis ≤ 14 palabras, body ≤ 30 palabras |
| **Comparative** | warm white | Slide 03 — modelo viejo vs sapiens | Dos columnas paralelas, 3 bullets cada una, máx 12 palabras por bullet |
| **Process** | warm white | Slide 04 — 3 a 5 pasos del método | 1 step "active" en teal (el clave), resto en blanco. Title de paso ≤ 4 palabras, descripción ≤ 16 palabras |
| **BigQuote** | cream `#F5F0EB` | Slide 05 — cita corta de un caso | Tag tipo `Caso real · 05 / NN`, quote ≤ 16 palabras, atribución con nombre + contexto. **Solo si hay caso real verificable.** Si no hay → omitir este slide. |
| **Stat** | teal-deep `#1E7A6D` | Slide 06 — un dato fuerte con fuente | Número grande (≤ 4 chars con sufijo), kicker explicando el dato, fuente verificable obligatoria |
| **CTA** | near-black `#1A1C23` | Slide 07 (último) — invitación a actuar | Headline ≤ 8 palabras, botón gold con flecha, handle `@sapiens.ed`, logo grande abajo |

### Ritmo cromático (regla dura)

Nunca dos slides consecutivos con la misma clase de surface. Patrón estándar:

```
01 Cover (teal) → 02 Thesis (warm) → 03 Comparative (warm + dark inset) →
04 Process (warm) → 05 BigQuote (cream) → 06 Stat (teal-deep) → 07 CTA (near-black)
```

El ojo del lector necesita warm-white entre golpes de color. Dos teal seguidos rompen el ritmo.

### Slides opcionales (puedes saltar si el tema lo pide)

- **BigQuote** — solo si hay caso real. En mes 1-3 (sin clientes en `pieces.sqlite` con `case_study=1`), **omitir BigQuote**.
- **Comparative** — útil cuando el tema admite contraste viejo/nuevo. Si el tema es puramente expositivo, saltarlo.
- **Stat** — solo si hay fuente verificable. Sin fuente = no Stat.

---

## Notas técnicas para `produce_carrusel_ds.py` y `render.py`

- Cada template es **autosuficiente**: tiene su propio `<style>` inline + referencia `../colors_and_type.css` para tokens y fuentes.
- Los templates asumen que viven en `slides/` y que `colors_and_type.css` + `assets/` + `fonts/` están en el directorio padre.
- Cuando se copien a `staging/<piece_id>/`, mantener la misma estructura: HTMLs en `staging/<piece_id>/slides/`, recursos en `staging/<piece_id>/`.
- `render.py` itera sobre `slides/slide-*.html` ordenados, abre cada uno con Playwright (1080×1350, device_scale_factor=2), captura PNG y lo escribe a `staging/<piece_id>/slide-NN.png` (al nivel del piece, no dentro de `slides/`).
- Los templates originales tienen artefactos `data-cc-id="cc-N"` del editor Claude Design — se pueden dejar (no afectan render) o limpiar si el LLM regenera el HTML completo.

---

## Costo estimado

~$0.10-$0.15 por carrusel (vs $0.065 del skill gestos). El extra viene del HTML completo en la respuesta del LLM. Aceptable: 1 pieza/semana ≈ +$0.40-$0.60/mes vs skill gestos.

---

*sapiens by shift — "tu ruta. diseñada con método. medida con datos."*
