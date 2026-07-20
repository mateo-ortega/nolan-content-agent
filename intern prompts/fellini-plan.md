# Plan — Funcionalidad UGC educativo con avatar IA via Higgsfield para Nolan

## Contexto

El objetivo es ampliar la base de reels de Sapiens en Instagram con contenido de ciencia pop (Pilar 1 viral del banco de guiones) sin saturar la agenda de grabación de Mateo. Actualmente Nolan tiene 4 formatos de producción (carrusel, carrusel-DS, animación Manim, voiceover+B-roll, guion-para-talking-head) y todos los reels con cara visible dependen de Mateo grabando. La nueva funcionalidad UGC suma un quinto formato: video vertical con avatar IA que habla un guion educativo, generado via Higgsfield MCP oficial (`https://mcp.higgsfield.ai/mcp`).

Decisiones tomadas con Mateo:
- **Proveedor:** Higgsfield MCP oficial (URL provista por Mateo). Si el catálogo de tools no expone Speak v2 directamente, fallback a SDK `higgsfield-client` Python.
- **Avatares:** DOS personajes consistentes via Soul ID.
  - **Carla** (alias provisional): mujer latina ~30, experta en ciencias sociales/educación. Look editorial cálido (sweater liso teal, fondo warm-white minimal). Voz contralto neutro-latam.
  - **Daniel** (alias provisional): hombre tech-académico ~38-42, mayor que Mateo para autoridad. Look smart-casual (camisa oxford, lentes, fondo abstracto teal-deep). Voz barítono español rioplatense/colombiano.
- **Rol:** Presentador alterno para temas de ciencia pop (Pilar 1). Mateo se queda con método pedagógico y demos físicas. Carla cubre ciencias sociales/educación/psicología del aprendizaje; Daniel cubre física/matemáticas/química/ingeniería.
- **Frecuencia:** 1 reel/semana. Entra al `cadence.yaml` como `ugc_avatar: 1`.

## Decisión arquitectónica — Agente separado "Fellini"

**Recomendación: agente separado con contexto fresco, no integración monolítica en Nolan.**

Razones:
1. El stack de UGC-avatar es ortogonal al resto de Nolan: prompt engineering cinematográfico, gestión de Soul IDs, validación post-render lipsync, edición vertical, subtítulos quemados. Mezclarlo dentro de Nolan ensucia su contexto.
2. Los DOS personajes requieren consistencia visual y de voz a través de múltiples piezas. Eso es estado que vive mejor en un agente dedicado.
3. La memoria global de Mateo prefiere "sesiones separadas" para tareas verticales complejas.
4. El MCP de Higgsfield no necesita estar registrado en Nolan; solo en Fellini. Menor superficie de ataque y menor latencia de tools.

**Arquitectura:**
```
Nolan (orquestador)
   |
   |-- nolan-decide-format -> elige "ugc_avatar" -> brief.yaml
   |-- nolan-produce-ugc-avatar (SKILL PUENTE, NO produce video)
   |     |
   |     |-- Valida brief, escribe orden en cola SQLite (queue_ugc.sqlite)
   |     |-- Invoca a Fellini: `claude --no-interactive --agent fellini --prompt "produce <piece_id>"`
   |     |-- Espera resultado (polling staging/<piece_id>/avatar.mp4)
   |     |-- Empaqueta y devuelve a Nolan
   |
   |-- nolan-package -> sube a Drive y notifica via Telegram

Fellini (agente Claude Code separado, contexto fresco)
   |
   |-- MCP: higgsfield (https://mcp.higgsfield.ai/mcp)
   |-- Skills propias:
   |     - fellini-guion-ugc       : adapta brief.yaml a guion ciencia-pop 30-45s
   |     - fellini-render-avatar   : llama Higgsfield Speak v2, genera MP4
   |     - fellini-postpro-vertical: subtítulos quemados (Whisper.cpp), endcard Sapiens
   |     - fellini-validate-ugc    : ética, lipsync score, safe-zone, duración
   |-- Catálogo de avatares en memory/avatares/{carla,daniel}.yaml con Soul IDs
   |-- Devuelve: staging/<piece_id>/{avatar.mp4, caption.md, metadata.json}
```

## Concepto de los DOS avatares

### Carla — "Ciencia social y aprendizaje"

| Campo | Valor |
|---|---|
| Edad aparente | 28-32 |
| Fenotipo | Latina, piel media, cabello castaño oscuro suelto u recogido casual |
| Vestuario base | Sweater de hilo liso teal oscuro `#1E7A6D` o camisa de lino warm-white |
| Lentes | Opcional, montura fina dorada |
| Setting | Fondo neutro warm-white con sombra suave, o textura abstracta teal-soft |
| Encuadre | Medio-corto vertical, mirada a cámara, leve angulación 5° |
| Voz | Contralto suave, español neutro-latam, ritmo pausado, sin energía hype |
| Temas | Psicología del aprendizaje, ciencias sociales, neuroeducación, historia de la ciencia |
| Soul ID | A generar en primer setup (5-7 fotos de referencia coherentes con la descripción) |

### Daniel — "Ciencia dura y tecnología"

| Campo | Valor |
|---|---|
| Edad aparente | 38-42 (mayor que Mateo para señalizar autoridad senior) |
| Fenotipo | Latino, piel media-clara, barba corta entrecana, pelo corto |
| Vestuario base | Camisa oxford gris claro o sweater de algodón gold-pale `#FFF5E0` con cuello de camisa |
| Lentes | Sí, montura negra acetato fino |
| Setting | Fondo abstracto teal-deep `#1E7A6D` con bokeh muy sutil, o pared de estudio gris cálido |
| Encuadre | Medio-corto vertical, mirada a cámara, autoridad serena |
| Voz | Barítono cálido, español colombiano-paisa con dejos neutros, ritmo controlado |
| Temas | Física, química, matemáticas, ingeniería, IA, tecnología |
| Soul ID | A generar en primer setup |

**Reglas de marca para ambos:**
- Sin gestos exagerados ni movimientos cinematográficos de cámara fuerte (mantener autoridad calmada de Sapiens).
- Acento de color teal o gold siempre presente (wardrobe o setting).
- Endcard final con wordmark `sapiens` (Outfit Bold) y CTA igual al de talking-head.
- Subtítulos en estilo Quote-Card Sapiens (Outfit Black 90pt CAPS, comillas en acento, keyword marcada).

## Archivos a crear / modificar

### En Nolan (proyecto actual)

**Crear:**
- `skills/nolan-produce-ugc-avatar/SKILL.md` — documenta when-to-use, inputs (brief.yaml), outputs, invocación a Fellini.
- `skills/nolan-produce-ugc-avatar/scripts/produce_ugc_avatar.py` — script puente, valida brief, encola en `staging/queue_ugc.sqlite`, lanza Fellini via `subprocess.run`, espera resultado, mueve assets a `staging/<piece_id>/`.
- `prompts/formats/ugc_avatar.md` — constraints del formato: 1080×1920 vertical, 25-45s, ciencia pop, hook honesto, sin clickbait, CTA Sapiens estándar.

**Modificar:**
- `skills/nolan-decide-format/scripts/decide_format.py` — añadir regla:
  ```python
  # Si pilar == "ciencia_pop" y semana sin ugc_avatar y persona == "carla" o "daniel"
  if topic_pilar == "ciencia_pop" and not weekly_quota_met("ugc_avatar"):
      return {"format": "ugc_avatar", "presenter": pick_presenter(topic_subarea), "confidence": 0.85}
  ```
- `skills/nolan-decide-format/SKILL.md` — documenta el nuevo formato y la lógica de presenter selection (Carla para sociales/educación, Daniel para STEM).
- `cadence.yaml` (o donde viva el mix semanal) — añadir `ugc_avatar: 1`.
- `skills/nolan-package/scripts/package.py` — agregar validación mínima del formato ugc_avatar (existe `avatar.mp4`, duración 25-45s, subs quemados detectados).
- `docs/nolan-roadmap-amplificacion.md` — anotar el nuevo formato y el agente Fellini.
- `HANDOFF.md` — sección Fellini con setup y dependencias.

### En Fellini (agente separado, repo nuevo o subfolder)

Crear directorio: `/home/teo/Desktop/Proyectos/fellini-ugc-avatar/`

**Estructura:**
```
fellini-ugc-avatar/
├── .claude/
│   ├── settings.json           # MCP de Higgsfield registrado
│   └── settings.local.json     # API keys locales
├── .mcp.json                   # URL https://mcp.higgsfield.ai/mcp
├── CLAUDE.md                   # Contexto: identidad de Carla/Daniel, marca Sapiens, reglas
├── memory/
│   ├── avatares/
│   │   ├── carla.yaml          # Soul ID, voz ID, prompt base, wardrobe, settings permitidos
│   │   └── daniel.yaml
│   └── brand_sapiens.md        # Sintesis de identidad para Fellini
├── skills/
│   ├── fellini-guion-ugc/
│   │   ├── SKILL.md
│   │   └── scripts/guion_ugc.py        # LLM (Sonnet) adapta brief → guion 25-45s
│   ├── fellini-render-avatar/
│   │   ├── SKILL.md
│   │   └── scripts/render_avatar.py    # Llama MCP higgsfield (o SDK fallback)
│   ├── fellini-postpro-vertical/
│   │   ├── SKILL.md
│   │   └── scripts/postpro.py          # Whisper.cpp subs + ffmpeg endcard
│   └── fellini-validate-ugc/
│       ├── SKILL.md
│       └── scripts/validate_ugc.py     # Lipsync score, duración, ética
├── scripts/
│   └── fellini_pipeline.py     # Orquesta las 4 skills en orden
├── staging/                    # Output compartido con Nolan
└── requirements.txt
```

## Librerías y dependencias

**Python (Fellini):**
- `mcp` o `fastmcp` — cliente MCP en Python si necesitas invocar el MCP fuera de Claude Code.
- `higgsfield-client` (fallback) — SDK oficial si el MCP no expone Speak v2.
- `openai-whisper` o `whisper-cpp-python` — transcripción para subs quemados (ya usado en `nolan-produce-voiceover`).
- `ffmpeg-python` — composición de endcard, subs, normalización audio.
- `pillow`, `numpy` — overlay de wordmark y safe-zone check (ya usado en Nolan).
- `pyyaml` — IO de briefs y catálogos de avatar.
- `pydantic` — validación de schemas brief.yaml.

**Nolan (skill puente):**
- Reutilizar lo existente. Solo `subprocess`, `sqlite3`, `pathlib`, `pyyaml` — todo en stdlib o ya instalado.

**Infraestructura:**
- Acceso a `https://mcp.higgsfield.ai/mcp` con credenciales Higgsfield (API key o token de cuenta).
- Cuenta Higgsfield con plan que cubra ~4 lipsync/mes (Pro $17-29/mes basta).
- FFmpeg en PATH (ya disponible para nolan-produce-voiceover).

## Pasos de implementación

### Fase 0 — Validación del MCP de Higgsfield (antes de codear nada)
1. Configurar el MCP en una instancia de Claude Code de prueba: `.mcp.json` con `{"mcpServers":{"higgsfield":{"url":"https://mcp.higgsfield.ai/mcp"}}}`.
2. Lanzar Claude Code y listar las tools expuestas por el MCP. Confirmar que existen tools tipo `speak`, `create_avatar`, `soul_train`, `status`, `download`.
3. Si el MCP solo expone modelos de video generativo (DoP, Soul) sin Speak, marcar fallback a SDK `higgsfield-client` y documentar en CLAUDE.md de Fellini.
4. Generar manualmente los dos Soul IDs (Carla y Daniel) usando 5-7 referencias visuales coherentes con la descripción. Guardar IDs en `memory/avatares/{carla,daniel}.yaml`.

### Fase 1 — Bootstrap de Fellini
1. Crear estructura de directorios en `/home/teo/Desktop/Proyectos/fellini-ugc-avatar/`.
2. Escribir `CLAUDE.md` con identidad de marca Sapiens (síntesis de `colors_and_type.css`, banco de guiones, restricciones de tono). Incluir reglas: "sin clickbait", "sin emojis", "tono cercano-experto", "duración 25-45s".
3. Escribir `.mcp.json` con la URL de Higgsfield y `settings.json` con permisos para las tools.
4. Crear `memory/avatares/carla.yaml` y `daniel.yaml` con: `name`, `soul_id`, `voice_id`, `wardrobe_palette`, `setting_palette`, `tematicas`, `prompt_base`.
5. Crear `memory/brand_sapiens.md` con paleta (#2B9E8F, #E8A838, etc), tipografía, tono.

### Fase 2 — Skills de Fellini
1. `fellini-guion-ugc`: prompt a Sonnet con brief.yaml + avatar.yaml + brand_sapiens.md → genera guion JSON con `hook`, `desarrollo`, `evidencia`, `cierre`, `cta`, `palabras_clave_subtitulos`. Restricciones duras: no superar 90 palabras (~40s a 135 wpm).
2. `fellini-render-avatar`: invoca el MCP de Higgsfield con `prompt` cinematográfico + `soul_id` + `voice_id` + `script`. Polling de status hasta completar. Descarga MP4 a `staging/<piece_id>/raw_avatar.mp4`.
3. `fellini-postpro-vertical`:
   - Whisper transcribe `raw_avatar.mp4` y genera SRT con timing por palabra.
   - FFmpeg quema subtítulos en estilo Quote-Card Sapiens (Outfit Black 90pt CAPS, comillas tipográficas, keyword en teal).
   - Compone endcard 2s con wordmark `sapiens` + CTA del guion.
   - Normaliza audio a -14 LUFS.
   - Output: `staging/<piece_id>/avatar.mp4`.
4. `fellini-validate-ugc`:
   - Duración entre 25 y 45s.
   - Detecta presencia de subs quemados (OCR sample).
   - Safe-zone para captions de Instagram (no en bordes superior/inferior 220px).
   - Pasa script por filtro ético (mismo de `nolan-package`).
   - Lipsync score básico: silabas habladas vs duración audio.

### Fase 3 — Pipeline de Fellini
1. `scripts/fellini_pipeline.py` recibe `--brief <path>` y `--piece_id <id>`. Orquesta las 4 skills en orden. Escribe `metadata.json` con resultado y errores.
2. Manejo de errores: si Higgsfield falla, retry con backoff 30s/120s/300s. Si supera retries, marca el brief con `status=failed` y notifica.

### Fase 4 — Integración con Nolan
1. Crear `skills/nolan-produce-ugc-avatar/SKILL.md` y `produce_ugc_avatar.py`:
   - Valida brief.yaml (campo `presenter` → {carla, daniel}, `pilar == ciencia_pop`).
   - Encola en `staging/queue_ugc.sqlite` con `piece_id`, `brief_path`, `enqueued_at`.
   - Lanza Fellini: `subprocess.run(["claude", "--no-interactive", "--cwd", CASSINI_DIR, "--prompt", f"produce {brief_path} {piece_id}"], timeout=900)`.
   - Polling: espera hasta 15 min por `staging/<piece_id>/avatar.mp4`.
   - Copia output a `nolan/staging/<piece_id>/` y escribe metadata.
2. Modificar `decide_format.py` con la regla del nuevo formato.
3. Modificar `cadence.yaml` con cuota semanal `ugc_avatar: 1`.
4. Modificar `nolan-package/package.py` para validar el nuevo formato.
5. Crear `prompts/formats/ugc_avatar.md` con constraints visibles para el decisor.

### Fase 5 — Verificación end-to-end
1. **Smoke test Fellini standalone:**
   - Crear `brief_test.yaml` con tema "por qué olvidamos sueños al despertar", presenter=carla.
   - Ejecutar `python scripts/fellini_pipeline.py --brief brief_test.yaml --piece_id TEST001`.
   - Verificar `staging/TEST001/avatar.mp4` existe, dura 25-45s, tiene subs quemados, endcard Sapiens visible.
   - Verificar consistencia visual de Carla con descripción del catálogo.
2. **Smoke test integración Nolan → Fellini:**
   - Forzar decisor con `--force-format ugc_avatar`.
   - Ejecutar el pipeline normal de Nolan.
   - Verificar que el output llega a `nolan/staging/<piece_id>/` y que `nolan-package` lo valida sin error.
3. **Validación de marca con muestra real:**
   - Generar 2 reels piloto (uno por presenter).
   - Revisar manualmente: ¿la cara de Carla coincide en ambos reels (Soul ID consistente)? ¿La voz suena natural en español? ¿El tono respeta el banco de guiones?
   - Si pasa, marcar formato como production-ready y habilitar el cron.
4. **Costo real medido tras 4 semanas:**
   - Logear consumo de créditos Higgsfield por video.
   - Validar que el plan Pro/Ultimate alcanza para 1 reel/semana sin caer en pay-per-use.

## Cómo se invoca al final

```bash
# Producción semanal automática (cron Hermes)
cd /path/to/nolan
python -m nolan.cli run-week --include ugc_avatar

# O manual single-piece
python skills/nolan-produce-ugc-avatar/scripts/produce_ugc_avatar.py \
    --brief staging/UGC042/brief.yaml \
    --piece_id UGC042
```

Internamente eso lanza:
```bash
claude --no-interactive \
       --cwd /home/teo/Desktop/Proyectos/fellini-ugc-avatar \
       --prompt "produce staging/UGC042/brief.yaml UGC042"
```

Y Fellini, con MCP de Higgsfield ya conectado, ejecuta su pipeline de 4 skills y devuelve el MP4.

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| MCP de Higgsfield no expone Speak v2 directamente | Media | Fallback a SDK `higgsfield-client` Python. Decidir en Fase 0 antes de codear. |
| Soul ID inconsistente entre piezas (Carla cambia de cara) | Media | Generar Soul ID con 7+ referencias muy controladas. Lock en YAML. Re-generar si drift >10%. |
| Voz IA suena robótica en español Colombia | Alta | Probar voces de ElevenLabs o de Higgsfield. Si ninguna pasa, clonar voz humana (no la de Mateo) con consentimiento. |
| Costo escala mal con 4 reels/mes | Baja | Plan Pro Higgsfield cubre folder; monitorear créditos. |
| Audiencia rechaza el avatar como inauténtico | Media-Alta | Disclaimer en bio: "algunos reels usan presentadores virtuales para temas que no requieren demo física". Tier 1 feedback loop semana 1 detecta caída de engagement. |
| Contexto de Nolan se contamina con stack UGC | Baja (mitigado por diseño) | Fellini es agente separado. Nolan solo conoce la interfaz de cola. |

## Framework de Fellini — análisis y decisión

| Framework | Estado MCP | Cold start | Estado persistente | Curva | Fit |
|---|---|---|---|---|---|
| **Claude Code CLI (sub-instancia)** | Nativo, ya conocido | Sí (5-15s por invocación) | Vía CLAUDE.md + memory/ | Cero (ya lo usas) | Bueno para invocaciones esporádicas |
| **Claude Agent SDK (Python)** | Nativo first-party Anthropic | No si corre como servicio | Sistema-prompt + memory custom | Baja-media | Ideal para servicio/daemon |
| **Segunda instancia Hermes en VPS** | Manual (cliente MCP propio) | No (Hermes vive corriendo) | SQLite + filesystem | Media (ya conocida para Aureliano) | Coherente con stack actual |
| **n8n / LangGraph / CrewAI** | Vía nodos comunidad | Variable | Sí | Alta | Sobreingeniería para esta tarea |

**Recomendación: Claude Agent SDK en Python, empaquetado como librería `fellini/` e invocado desde Nolan.**

Razones:
1. Latencia controlada. El SDK permite mantener sesión cliente con system-prompt cacheado entre invocaciones. Frente a Claude Code CLI, que arranca un proceso entero cada vez, el SDK puede correr como módulo Python embebido o como microservicio FastAPI.
2. MCP first-party. El SDK tiene soporte oficial para MCP (`anthropic.MCPClient`). Conecta a `https://mcp.higgsfield.ai/mcp` sin hacks.
3. Tooling propio sin SKILL.md. Fellini necesita tools muy específicas (`render_avatar(soul_id, script)`, `validate_lipsync(mp4)`). Con el SDK las defines como funciones Python con docstring.
4. Aislamiento real. Fellini como librería Python vive en su propio venv, su propio `requirements.txt`, su propio test suite.
5. Coherencia con Hermes futuro. El SDK Python es portable al VPS donde corre Hermes.

## Análisis de costo — Higgsfield vs alternativas (4 reels/mes, ~35s cada uno)

| Proveedor | Plan recomendado | Costo USD/mes | Costo/reel | Notas |
|---|---|---|---|---|
| **Higgsfield Pro (anual)** | $17/mes | **$17** | **$4.25** | 150 créditos/mes. MCP oficial ya provisto. |
| **Higgsfield Ultimate** | $29/mes anual | $29 | $7.25 | Soul ID dedicado, más resolución, prioridad de cola |
| **HeyGen API pay-as-you-go** | Sin plan | $2.33-9.33 | $0.58-2.33 | $1/min std, $4/min Avatar IV. MCP oficial Anthropic. |
| **Hedra Creator (Character-3)** | $9/mes anual | $9 | $2.25 | 100 créditos/mes. Buena para avatares no foto-realistas. |

**Decisión de costo:**
1. Empezar con Higgsfield Pro anual ($17/mes). Cubre 4 reels con créditos para iteración. MCP oficial ya integrado.
2. NO contratar ElevenLabs en Fase 0. Probar primero las voces nativas de Higgsfield Speak v2.
3. Si en mes 3-4 quieres pasar a 2 reels/semana (8/mes), Higgsfield Pro alcanza si no hay muchos retries. Si retries crecen, upgrade a Ultimate $29.

**Costo total mensual end-to-end con Higgsfield Pro:**

| Componente | Costo |
|---|---|
| Higgsfield Pro | $17 |
| Anthropic API (Sonnet 4.6) | $1.20 |
| ElevenLabs Creator (opcional) | $22 |
| **Total mensual** | **$18.20 sin voz clonada / $40.20 con voz clonada** |

## Notas finales

- No tocar CTAs ni estilo de carruseles (regla feedback intocable en memoria).
- Subtítulos siguen estilo Quote-Card Sapiens definido en `feedback_reels_quote_card.md`.
- Si Mateo decide pivot a HeyGen luego, la abstracción en `fellini-render-avatar` permite swap del proveedor sin tocar el resto del pipeline.
- Documentar todo aprendizaje de la Fase 0 en `fellini-ugc-avatar/CLAUDE.md` para que próximas sesiones no repitan el descubrimiento del catálogo de tools del MCP.
- Nombre unificado: el agente, su directorio (`fellini-ugc-avatar/`) y todos los scripts y skills usan el slug `fellini`. El codename interno previo `cassini` queda obsoleto.
