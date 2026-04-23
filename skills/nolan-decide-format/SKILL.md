---
name: nolan-decide-format
description: Dado un tema con nicho y fuentes, decide el formato óptimo (carrusel, animación Manim, voiceover+b-roll, guion talking-head) y un arquetipo narrativo. Aplica reglas declarativas antes de delegar al LLM. Output es un brief estructurado para la skill de producción correspondiente.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [strategy, sapiens, nolan]
    category: sapiens
    requires_toolsets: [terminal]
---

# nolan-decide-format

Decide **formato** y **arquetipo** para un tema ya puntuado por `nolan-research`. Reglas declarativas primero; LLM solo si las reglas dejan ambigüedad.

## When to use

- Tras `nolan-research` con un tema en shortlist.
- Usuario envía `/tema` — salta research si viene con fuentes adjuntas.

## EJECUCIÓN

**Nolan NO aplica estas reglas con su propio modelo.** Invocar siempre el script:

```bash
python3.12 /srv/sapiens-nolan/skills/nolan-decide-format/scripts/decide_format.py \
    --topic "<descripción del tema>" \
    --niche <nicho>
```

El script aplica las reglas declarativas primero y solo delega al LLM (DeepSeek) si la confianza es < 0.7. El output es un brief YAML listo para `nolan-produce-carrusel`.

## Formatos disponibles

| Formato | Cuándo |
|---|---|
| `carrusel` | Densidad informativa media-alta, lista enumerable, comparativa, framework. Default para L1 (padres, jóvenes) con texto protagonista. |
| `animacion` | Conceptos matemáticos/físicos/químicos donde visualizar la transformación es el valor. Solo 1-2 por semana (costo alto de render Manim). |
| `voiceover_broll` | Narrativa emocional o storytelling corto (15-30s), usa b-roll stock. Bueno para L1 testimoniales y L2 casos de uso. |
| `talking_head` | Guion para Mateo cuando (a) el tema pide cara humana por credibilidad, (b) es una postura editorial, (c) una respuesta a audience sincera. Nolan produce solo el guion (script.md) — Mateo graba. |

## Reglas declarativas (en orden)

1. **Si tema contiene fórmula matemática o transformación paso a paso** → `animacion`. (sig: presencia de `$$...$$`, palabras `derivada`, `integral`, `reacción`, `cinética`, `binomio`, etc.)
2. **Si tema es opinión editorial o postura de marca** → `talking_head`. (sig: palabras `por qué creemos`, `nuestra postura`, `mi experiencia como`, `me preguntan mucho`.)
3. **Si tema es testimonial o arco narrativo** → `voiceover_broll`. (sig: palabras `caso de`, `historia de`, `cómo pasó X a Y`.)
4. **Default para L1 con densidad informativa** → `carrusel` con arquetipo según contenido:
   - Lista numerada → `senales`
   - Tesis única con pasos → `tesis`
   - A vs B → `comparativa`
   - Pasos ejecutables → `framework`
   - Estructura libre del guion → `ad_hoc`
5. **Default para L2 (adultos IA)** → `carrusel` a menos que aplique regla 2 o 3.

Si dos reglas chocan, gana la de número menor. Si ninguna aplica con confianza > 0.7, **delegar a LLM** (`strategy.decide_format` → DeepSeek) con prompt estructurado.

## Output (brief para skill de producción)

```yaml
piece_id: 2026-04-22-icfes-lectura-critica-metodo
niche: jovenes_preicfes
format: carrusel
archetype: framework
hook: "no es memoria. es método."
thesis: "La lectura crítica ICFES se resuelve con un método de 3 pasos, no estudiando más."
pillars:
  - { name: "identificar_argumento", body: "..." }
  - { name: "separar_premisa_de_opinion", body: "..." }
  - { name: "verificar_coherencia", body: "..." }
sources:
  - { url: "...", type: "icfes_official", citation: "..." }
tone_calibration: "jovenes_directo_sin_paternalismo"
slides_count_estimate: 7
production_skill: nolan-produce-carrusel
ethics_risk_estimate: low
estimated_production_cost_usd: 0.12
```

## Pitfalls

- **Regla 1 (matemáticas) es voraz**: no todo tema con un número va a Manim. Exigir fórmula real o transformación paso a paso, no solo "subir 40 puntos".
- **Talking head sobra-usado**: reservar para 10% semanal máximo (ver `cadence.yaml`). Si Mateo lo pide explícito por `/formato talking_head`, obedecer.
- **Arquetipo `ad_hoc`** es el último recurso. Si el tema no encaja en senales/tesis/comparativa/framework, probablemente el tema es muy vago — devolver a shortlist con flag `needs_narrowing`.

## Verification

```bash
hermes chat "decide_format --topic 'ICFES lectura crítica método 3 pasos' --niche jovenes_preicfes"
# Esperado: brief YAML con format=carrusel, archetype=framework, slides_count_estimate entre 6-8
```
