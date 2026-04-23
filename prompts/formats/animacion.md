# Formato: animacion (Manim)

## Cuándo usar este formato

Solo cuando el valor de la pieza está en **ver la transformación sucediendo**: una derivada siendo calculada, un binomio expandiéndose, una reacción química equilibrándose, un concepto geométrico emergiendo. Si la transformación se puede describir en texto, usar carrusel.

Duración objetivo: **15–28 segundos**. Máximo 35s (Instagram penaliza retención baja en Reels largos).

## Estructura narrativa de la escena

```
[0–3s]   Título / hook visual — texto animado que plantea la pregunta
[3–Xs]   Desarrollo — la transformación paso a paso (el valor de la pieza)
[X–Ys]   Resultado / revelación — el "aha" visual
[Y–fin]  Cierre — micro-acción o insight + wordmark sapiens 2s
```

## Clases Manim y convenciones de código

- Heredar siempre de `SapiensScene` (definida en `sapiens_theme.py`) para obtener paleta, tipografías y logo automáticos.
- Color principal de ecuaciones: `SAPIENS_GOLD = "#E8A838"` para el término clave.
- Color secundario: `SAPIENS_TEAL = "#2B9E8F"` para el resultado.
- Fondo: `SAPIENS_DARK = "#0B0D12"` (fijo en animaciones — excepción al light mode).
- Fuente matemática: `MathTex` con template `SapiensTexTemplate` (LuaLaTeX + Jura).
- Resolución: 1080×1920 (vertical), 60fps (`-qh` flag Manim).
- Nombre de archivo clase: `SAPIENS_<slug>_v<N>` (ej. `SAPIENS_binomio_cuadrado_v3`).

## Guion de escena (output del copywriter)

El copywriter genera un archivo Python con la escena. Debe incluir:

```python
# NOLAN_SCENE_BRIEF: {
#   "topic": "...",
#   "duration_target_s": 22,
#   "voiceover_text": "...",  # si aplica
#   "key_formula": "...",
#   "nicho": "..."
# }

from sapiens_theme import SapiensScene, SAPIENS_GOLD, SAPIENS_TEAL

class SAPIENS_<Slug>_v1(SapiensScene):
    def construct(self):
        # Implementación de la escena
        ...
```

## Reglas de duración y complejidad

- Máx 3 transformaciones animadas por escena. Si el tema necesita más, dividir en 2 piezas.
- Cada `Transform` / `Write` / `FadeIn` debe durar al menos 0.5s — sin animaciones rápidas incomprensibles.
- Si el concepto requiere LaTeX complejo: validar primero con `py -3.12 -m py_compile scene.py` y renderizar en calidad baja (`-ql`) antes del render final.

## Voiceover (opcional)

Si el brief pide narración de voz:
- `voiceover_text` en el guion: ≤140 palabras para 25s, español neutro, sin jerga técnica.
- Tiempo los `self.wait()` para que coincidan con los beats del voiceover.
- ElevenLabs parámetros sugeridos: `stability=0.40, similarity_boost=0.85, style=0.20`.

## Ejemplo de brief input

```yaml
topic: "Expansión del binomio (a+b)²"
key_formula: "(a+b)^2 = a^2 + 2ab + b^2"
nicho: "jovenes_preicfes"
niche_note: "mostrar la demostración geométrica — el cuadrado en papel"
duration_target_s: 22
voiceover: false
```
