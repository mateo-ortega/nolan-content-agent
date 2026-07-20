# HANDOFF — Proyecto Nolan (Sapiens by Shift)

**Fecha de última actualización:** 2026-05-18
**Estado global:** Pipeline completo end-to-end operativo en VPS. Carrusel v1 + carrusel-DS + animación Manim + talking-head (reels-postpro) + research + callbacks + learning loop corriendo bajo systemd. rclone Drive configurado y operativo. **@sapiens.ed comienza a publicar el 2026-05-19.** Próximo hito: Tier 1 feedback loop (semana del 19 mayo).

---

## 1. Contexto del proyecto

**Nolan** es el agente de contenido de **@sapiens.ed** (Sapiens by Shift — línea educativa de la agencia de IA de Mateo). Produce carruseles, animaciones Manim, voiceovers y guiones para Instagram. **Nunca publica** — deja cada pieza en `staging/<piece_id>/` y notifica a Mateo por Telegram para aprobación manual.

### Arquitectura

```
Mateo (Telegram) ──► Hermes Agent (VPS) ──► skills/nolan-*/scripts/*.py
                         │                         │
                         │                         ├──► sapiens.nolan_llm_router  (routing a modelos correctos)
                         │                         ├──► sapiens.ethics_gate       (semáforo SOUL)
                         │                         └──► skills/sapiens-carrusel/assets/render.py  (Playwright+Jinja)
                         │
                         └──► staging/<piece_id>/ (artefactos) ──► Drive (rclone) ──► Telegram (preview + botones)
```

### Principios NO negociables

- **Silencio durante producción**: Nolan nunca notifica paso a paso. Solo tres casos rompen silencio: pieza lista (aprobación), decisión humana bloqueante, bloqueo crítico. Definido en `SOUL.md` y `AGENTS.md`.
- **Routing de modelos estricto**: Nolan NO genera content.yaml, captions ni clasificaciones con Sonnet como modelo conversacional. Todo pasa por scripts Python en `skills/nolan-*/scripts/`, que usan `sapiens.nolan_llm_router` para enrutar: DeepSeek para research/clasificación, Sonnet solo para copy final, Perplexity para web search.
- **Budget**: $50 USD/mes hard cap. Warn 70%, kill 90%, hard stop 100%.

---

## 2. Infraestructura

### VPS (Hostinger KVM 2)

- **IP**: `<VPS_IP>`
- **OS**: Ubuntu 24.04 LTS
- **Usuario**: `<usuario_vps>` (sudo)
- **SSH**: key ed25519 desde Windows, puerto 22 único abierto (UFW activo)
- **Tree del proyecto**: `/srv/sapiens-nolan/`
- **Venv**: `/srv/nolan-venv/` (Python 3.12.3) — activar con `source /srv/nolan-venv/bin/activate`

### Stack instalado

- Python 3.12.3, FFmpeg 6.1.1, LuaLaTeX (TeX Live 2023), Manim 0.20.1
- Playwright + Chromium headless
- rclone 1.60.1 (configurado, remote `gdrive_sapiens` operativo)
- SQLite 3.45.1, Docker 29.4.0
- Fuentes Sapiens en `/usr/share/fonts/sapiens/`: Outfit, Instrument Sans, Geist Mono, Jura
- Swap 8 GB

### Hermes Agent

- Binario: `/home/mateo/.local/bin/hermes`
- Config: `~/.hermes/`
  - `SOUL.md` (personalidad inyectada en system prompt slot 1)
  - `AGENTS.md` (convenciones)
  - `.env` (API keys)
  - `skills/` (skills registradas)
- **Modelo base de Hermes**: `deepseek/deepseek-chat` via OpenRouter (cambio reciente para reducir costos — Sonnet se sigue usando SOLO dentro de los scripts Python para copy de alta calidad)
- **Systemd service**: `hermes-gateway.service` (enabled, running) — maneja el gateway Telegram

### Secrets configurados (`~/.hermes/.env`)

- `OPENROUTER_API_KEY` ✅
- `TELEGRAM_BOT_TOKEN` ✅
- `TELEGRAM_ALLOWED_USERS=<TELEGRAM_USER_ID>` (ID Mateo) ✅

### Secrets pendientes

- `ELEVENLABS_API_KEY` (para `nolan-produce-voiceover` cuando se implemente)
- `PEXELS_API_KEY`, `PIXABAY_API_KEY` (b-roll para voiceover — aún no implementado)
- `IG_HANDLE=sapiens.ed` en `.env` (necesario para `nolan-analytics` — Tier 1)

---

## 3. Estructura del repo

```
/srv/sapiens-nolan/                 (VPS)
c:\Users\USUARIO\Desktop\Proyectos\nolan-content-agent\   (Windows local)
│
├── SOUL.md                          # Personalidad Nolan — Mateo edita
├── AGENTS.md                        # Convenciones operativas — Mateo edita
├── README.md                        # Doc de alto nivel — Mateo edita
├── HANDOFF.md                       # ESTE ARCHIVO — actualizar en cada hito
├── requirements-nolan.txt           # httpx, pyyaml, pillow, python-dotenv
│
├── sapiens/                         # Librería Python compartida
│   ├── __init__.py
│   ├── nolan_llm_router.py          # ✅ Routing a modelos (OpenRouter / Perplexity)
│   └── ethics_gate.py               # ✅ Semáforo regex contra config/ethics.yaml
│
├── skills/                          # Skills Hermes (cada una con SKILL.md + scripts/)
│   ├── sapiens-carrusel/            # Renderer Playwright+Jinja (pre-existente, Sapiens kit)
│   │   └── assets/
│   │       ├── render.py            # Renderer principal (Playwright)
│   │       ├── config.yaml          # Config global (paleta, fuentes)
│   │       └── templates/
│   │           ├── portada.html
│   │           ├── interior.html    # Delega a macros según `gesto`
│   │           ├── cta.html
│   │           └── _macros.html     # 6 gestos: tachadura, escala, repeticion, inversion, bloque (NO usar), fragmentacion (NO usar)
│   │
│   ├── nolan-llm-router/SKILL.md    # Spec only (código vive en sapiens/)
│   ├── nolan-research/SKILL.md      # ⚠️ Script NO implementado
│   ├── nolan-decide-format/
│   │   ├── SKILL.md
│   │   └── scripts/decide_format.py # ✅ Reglas declarativas + fallback DeepSeek
│   ├── nolan-produce-carrusel/
│   │   ├── SKILL.md
│   │   └── scripts/produce_carrusel.py  # ✅ Pipeline completo
│   ├── nolan-produce-animacion/SKILL.md # ⚠️ Script NO implementado
│   ├── nolan-produce-voiceover/SKILL.md # ⚠️ Script NO implementado
│   └── nolan-package/
│       ├── SKILL.md
│       └── scripts/package.py       # ✅ Validación + Drive sync + Telegram notify
│
├── config/                          # Configs declarativas YAML
│   ├── llm_routing.yaml             # task → modelo (leído por nolan-llm-router)
│   ├── budget.yaml                  # pricing + umbrales (leído por BudgetGuard)
│   ├── ethics.yaml                  # Reglas regex red/yellow (leído por EthicsGate)
│   ├── benchmarks.yaml              # Polar stars + cuentas benchmark IG
│   ├── cadence.yaml                 # Calendario L-W-V + targets/semana
│   └── sources.yaml                 # Fuentes aprobadas para research
│
├── memory/                          # Estado persistente
│   ├── brand_context.md             # Resumen de marca Sapiens (inyectado en system prompt cacheado)
│   ├── trends.sqlite                # ⚠️ NO inicializado
│   └── pieces.sqlite                # ⚠️ Se crea automáticamente en package.py
│
├── staging/                         # Piezas en revisión
│   ├── fixtures/
│   │   ├── brief-icfes-lectura-critica.yaml   # Brief de ejemplo
│   │   └── content_min.yaml         # ✅ Fixture para dry-run (schema nativo render.py)
│   └── <piece_id>/                  # Piezas reales generadas
│
├── logs/
│   ├── agent.log
│   ├── llm_usage.jsonl              # Una línea por llamada LLM (router escribe aquí)
│   ├── research.log
│   └── gateway.log
│
└── drive-mount/                     # rclone mount Google Drive (NO configurado aún)
    ├── staging/
    ├── aprobados/
    ├── rechazados/
    └── brand-assets/
```

---

## 4. Estado de implementación

> Última revisión: 2026-05-18. Las secciones 4.1–4.7 documentan lo que estaba implementado al 2026-04-20. Lo implementado desde entonces se lista en §4.8.

### ✅ COMPLETADO

#### 4.1. Librería `sapiens/`

**`sapiens/nolan_llm_router.py`**
- Clase `LLMRouter` con `call(task, messages, cache_system, piece_id)` → `LLMResponse`
- Carga `config/llm_routing.yaml` para mapear task → modelo
- Soporta OpenRouter (anthropic/claude-sonnet-4.6, deepseek/deepseek-chat) y Perplexity directa (sonar-pro)
- **Prompt caching Anthropic**: aplica `cache_control: ephemeral` al system message cuando `cache_system=True`
- `BudgetGuard`: `fcntl.flock` para thread-safety al escribir `logs/llm_usage.jsonl`, kill-switch a 90% del cap mensual
- `load_router()` factory desde env + config

**`sapiens/ethics_gate.py`**
- `EthicsGate.check(texts, sources_available)` → `EthicsResult(status, rule_id, description, matched_text)`
- Semáforo: `red` (abort), `yellow` (warn), `green` (pass)
- Maneja reglas regex estándar, coocurrencias (`competitor_name_attack`), emojis unicode (conversión JS→Python)
- `load_gate()` factory desde `config/ethics.yaml`

#### 4.2. Script `skills/nolan-produce-carrusel/scripts/produce_carrusel.py`

CLI: `--brief <path>`, `--dry-run`, `--piece-id <override>`

Pipeline:
1. Lee brief YAML
2. Genera `content.yaml` vía LLM (task `copy.carrusel_yaml` → Sonnet con cache de system) — en dry-run copia `content_min.yaml`
3. Valida schema nativo del renderer (tipo portada/interior/cta, gestos permitidos, comillas rectas)
4. Ethics pre-render sobre todos los textos de slides
5. Llama a `render.py` (Playwright) con `output_base = staging/` — el renderer crea `staging/{nombre}/` usando el campo `nombre` del YAML (= piece_id)
6. Genera `caption.md` (task `copy.final_caption` → Sonnet cached)
7. Ethics sobre caption
8. Construye `alt_text.md`, `sources.md`, `cover.jpg` (copia slide-01), `preview.jpg` (thumbnail 480x600)
9. Escribe `metadata.json` con piece_id, costo LLM total, ethics score, etc.

**Schema YAML nativo del renderer** (usado por el prompt del LLM y validado):
```yaml
nombre: '<piece_id>'          # CRÍTICO: determina subcarpeta de salida
titulo: 'Título display'
slides:
  - tipo: portada
    hero_pre: 'texto antes '
    hero_accent: 'palabra_dorada'
    hero_post: '. texto después.'
    subline: 'subtítulo'
  - tipo: interior
    label_indice: 'paso 1'
    eyebrow: '01 · LABEL'
    gesto: tachadura        # permitidos: tachadura, escala, repeticion, inversion
    g: { ...campos del gesto... }
  - tipo: cta
    hero: 'sapiens'
    tagline: 'aprende a tu medida'
    bio_text: 'Guardá esto.'
```

**Gestos** (definidos en `skills/sapiens-carrusel/assets/templates/_macros.html`):
| Gesto | Campos `g` | Cuándo |
|---|---|---|
| `tachadura` | pre, strike, mid, emphasis, post, body | Contraste "error vs verdad" |
| `escala` | pre, accent, post, subline | Resaltar UN concepto (texto MUY corto) |
| `repeticion` | words[], body | Refuerzo de término clave |
| `inversion` | pre, flipped, post, body | Sorpresa visual |
| `bloque` | — | **NO USAR** — rectángulo dorado que tapa texto |
| `fragmentacion` | — | **NO USAR** — complejo, posicionamiento absoluto |

#### 4.3. Script `skills/nolan-package/scripts/package.py`

CLI: `--piece-id <id>`, `--dry-run`

Pipeline:
1. Valida archivos obligatorios (`content.yaml`, `metadata.json`, `caption.md`, `alt_text.md`, `sources.md`, `slide-*.png`) y campos obligatorios en metadata
2. Ethics final check
3. Construye `preview.jpg` desde `cover.jpg` si falta
4. Upserta fila en `memory/pieces.sqlite` con estado `pending_review`
5. Sincroniza a Drive vía `rclone copy` (3 reintentos) — omitido si `RCLONE_REMOTE` no está
6. Envía a Telegram:
   - `sendMediaGroup` con los primeros 10 slides (caption en el primero)
   - `sendMessage` con botones inline: Aprobar / Rechazar / Editar / Ver en Drive
7. Guarda `telegram_message_id` en sqlite

**Tokens de Telegram**: lee `HERMES_TELEGRAM_BOT_TOKEN` O `TELEGRAM_BOT_TOKEN` (fix aplicado).

#### 4.4. Script `skills/nolan-decide-format/scripts/decide_format.py`

CLI: `--topic <texto>`, `--niche <id>`

- Reglas declarativas en orden: (1) fórmula/paso-a-paso → `animacion`; (2) opinión editorial → `talking_head`; (3) testimonial → `voiceover_broll`; (4) default L1/L2 → `carrusel`
- Asigna arquetipo: `senales` / `tesis` / `comparativa` / `framework` / `ad_hoc`
- Fallback a LLM (`strategy.decide_format` → DeepSeek) si confianza < 0.7
- Output: brief YAML listo para `nolan-produce-carrusel`

#### 4.5. Configs y personalidad

- `SOUL.md`: sección "Silencio durante producción" + "No genero content.yaml con mi propio modelo"
- `AGENTS.md`: "Routing de modelos — NO negociable" + "Silencio durante producción"
- `skills/nolan-produce-carrusel/SKILL.md` y `skills/nolan-decide-format/SKILL.md`: sección "EJECUCIÓN" que fuerza invocación del script

#### 4.6. Deploys al VPS (comprobados funcionando)

- `sapiens/nolan_llm_router.py`, `sapiens/ethics_gate.py`, `sapiens/__init__.py` → `/srv/sapiens-nolan/sapiens/`
- `skills/nolan-produce-carrusel/scripts/produce_carrusel.py` → VPS
- `skills/nolan-package/scripts/package.py` → VPS
- `skills/nolan-decide-format/scripts/decide_format.py` → VPS
- `staging/fixtures/content_min.yaml` → VPS
- `requirements-nolan.txt` instalado en venv

#### 4.7. Prueba actual (2026-04-20)

- **Dry-run**: `python3.12 skills/nolan-produce-carrusel/scripts/produce_carrusel.py --brief staging/fixtures/brief-icfes-lectura-critica.yaml --dry-run` → OK (5 slides placeholder, costo $0)
- **Render real**: mismo comando sin `--dry-run` → genera 7 slides PNG con Playwright en `staging/2026-04-22-icfes-lectura-critica-metodo/`

#### 4.8. Implementado desde 2026-04-20 (hitos adicionales)

- **`nolan-produce-animacion`**: Manim operativo (3 templates: BarChart, CurveReveal, StepReveal). Safe zone check post-render con `animacion_check.py`. Integrado al ciclo martes/viernes.
- **`nolan-produce-carrusel-ds`**: 7 templates HTML magazine-layout. Render vía Playwright. Jueves automático.
- **`nolan-produce-guion`**: script teleprompter 30-60s para Mateo. ⚠️ Defectos conocidos: emoji 🎥, hashtags, sin EthicsGate, sin caching — requiere fix.
- **`nolan-callbacks`**: handlers `/aprobar`, `/rechazar`, `/editar` implementados como scripts Python.
- **`nolan-learning`**: `rule_writer.py` + `apply_rule.py`. Cron domingo 18:00 Bogotá. Analiza rechazos ≥3 ocurrencias. Propone reglas vía DeepSeek, aprobación por Telegram antes de aplicar.
- **`nolan-research`**: Tavily + DuckDuckGo + Apify + RSS. Escribe a `memory/trends.sqlite`.
- **`reels-postpro/`**: módulo Python 1166 LOC para post-producción de talking-heads. Whisper ES + face-track + subtítulos ASS Sapiens + denoise + loudnorm -16 LUFS. 7 sesiones procesadas a mayo-17.
- **rclone Drive**: configurado y operativo. `RCLONE_REMOTE` presente en `.env` VPS.
- **`nolan-llm-router` con NIM fallback**: DeepSeek v4 Flash vía NVIDIA NIM (gratuito, 40 RPM) + fallback OpenRouter. Costo actual ~$7/mes.
- **`memory/trends.sqlite`**: schema completo e inicializado.
- **`memory/pieces.sqlite`**: operativo, actualizado por package.py y callbacks.

---

### ⚠️ PENDIENTE

#### 5.1. Fix `nolan-produce-guion` (prioridad baja)

`skills/nolan-produce-guion/scripts/produce_guion.py` tiene defectos menores:
- Incluye emoji 🎥 en output
- Incluye hashtags (prohibidos por brand_context)
- No pasa por EthicsGate
- No usa prompt caching para brand_context.md

Fix estimado: 1-2 horas. Editar `produce_guion.py` + SKILL.md.

#### 5.2. Backup SQLite automático

`memory/pieces.sqlite` y `memory/trends.sqlite` viven en VPS sin replicación. Un crash = perder el historial de aprendizaje y aprobaciones.

Implementar `scripts/backup.sh`: `rclone copy memory/*.sqlite gdrive_sapiens:SapiensContent/backups/` + cron 3AM Bogotá. Ver Tier 5.1 del roadmap.

#### 5.3. Smoke test full pipeline

`scripts/smoke_tests.sh` existe pero no cubre el ciclo completo. Pendiente: añadir validación de dimensiones PNG, costo < $0.30/pieza, ethics green como pre-flight del `ciclo.sh`. Ver Tier 5.2 del roadmap.

#### 5.4. Voiceover end-to-end

Formato pendiente del plan original. Bloqueado por reference recording (30 min de Mateo → ElevenLabs voice clone). Ver Tier 5.4 del roadmap. Esfuerzo: L (5-7 días).

#### 5.5. Pendientes menores

- `package.py`: `sendMediaGroup` + `sendMessage` duplicados — evaluar si eliminar uno.
- `~/.hermes/config.yaml`: verificar que `timezone: 'America/Bogota'` esté seteado.

#### 5.6. Prompts operativos unificados (investigación → guionización)

Los archivos en `prompts/` contienen piezas modulares (system prompts, calibración por nicho, specs de formato), pero **no existían prompts autocontenidos listos para copiar y pegar** que un humano o script pueda usar directamente contra una IA.

**Creados el 2026-04-22** — 4 prompts operativos que unifican marca + ética + formato en un solo bloque:

| # | Prompt | Modelo target | Input | Output |
|---|--------|---------------|-------|--------|
| 1 | **Investigador** | DeepSeek | Tema en bruto | Research brief YAML (datos verificados, ángulo editorial, formato recomendado, riesgo ético) |
| 2 | **Guionista Carrusel** | Sonnet | Research brief | `content.yaml` (slides con gestos para render.py) + `caption.md` |
| 3 | **Guionista Animación** | Sonnet | Research brief | `guion_animacion.yaml` (beats, LaTeX, instrucciones Manim) + caption |
| 4 | **Guionista Talking Head** | Sonnet | Research brief | `script.md` (guion para Mateo a cámara sin edición) + caption |

**Flujo obligatorio**: siempre Prompt 1 primero → su output alimenta Prompt 2, 3 o 4 según el formato recomendado.

**Ubicación**: `prompts/operativos/pipeline_investigacion_guiones.md` (documento consolidado con los 4 prompts completos y variables `{{VARIABLE}}` para reemplazar).

**Relación con scripts existentes**: estos prompts son la versión "manual" del pipeline. Cuando los scripts estén implementados (`research.py`, `produce_animacion.py`, `produce_voiceover.py`), los prompts se embeben dentro del código como templates — similar a como `produce_carrusel.py` ya embebe `_CARRUSEL_SYSTEM_TEMPLATE`. Mientras tanto, sirven para producción manual con cualquier interfaz de IA.

---

## 6. Comandos útiles

### Desde Windows (PowerShell)

```powershell
# Subir archivo puntual al VPS
scp "C:\Users\USUARIO\Desktop\Proyectos\nolan-content-agent\<path>" <usuario_vps>@<VPS_IP>:/srv/sapiens-nolan/<path>

# SSH al VPS
ssh <usuario_vps>@<VPS_IP>

# Descargar carrusel generado
scp -r <usuario_vps>@<VPS_IP>:/srv/sapiens-nolan/staging/<piece_id> "C:\Users\USUARIO\Desktop\<nombre>"
```

### En el VPS

```bash
# Activar venv
source /srv/nolan-venv/bin/activate
cd /srv/sapiens-nolan

# Dry-run producción carrusel
python3.12 skills/nolan-produce-carrusel/scripts/produce_carrusel.py \
    --brief staging/fixtures/brief-icfes-lectura-critica.yaml --dry-run

# Render real
python3.12 skills/nolan-produce-carrusel/scripts/produce_carrusel.py \
    --brief staging/fixtures/brief-icfes-lectura-critica.yaml

# Empaquetar (envía a Telegram)
python3.12 skills/nolan-package/scripts/package.py \
    --piece-id 2026-04-22-icfes-lectura-critica-metodo

# Dry-run package (sin Telegram ni Drive)
python3.12 skills/nolan-package/scripts/package.py \
    --piece-id 2026-04-22-icfes-lectura-critica-metodo --dry-run

# Ver último uso de LLMs
tail -20 logs/llm_usage.jsonl

# Status Hermes service
sudo systemctl status hermes-gateway
sudo journalctl -u hermes-gateway -f --lines 50

# Reiniciar Hermes tras editar SOUL.md / AGENTS.md / skills/*.md
sudo systemctl restart hermes-gateway
```

---

## 7. Bugs conocidos resueltos (lecciones aprendidas)

Registrados para que no vuelvan a pasar:

1. **Tildes desaparecían** — el prompt decía "ASCII" y el LLM lo interpretó como quitar acentos. **Fix**: aclarar que la regla ASCII es solo para comillas, y agregar regla explícita de "ortografía española perfecta OBLIGATORIA".

2. **Slides en blanco** — tres causas: (a) YAML con `layout: cover/body/cta` pero render.py espera `tipo: portada/interior/cta`; (b) render.py guarda slides en `{output_base}/{nombre}/` pero el código buscaba en `{output_base}/` directamente; (c) los slides `interior` requieren `gesto` + dict `g:` — sin eso el template renderiza nada. **Fix**: reescribir `_CARRUSEL_SYSTEM_TEMPLATE` con schema nativo, pasar `PROJECT_ROOT/staging/` como output_base, validar gesto+g en `_validate_content_yaml`.

3. **Bloque dorado "censuraba" texto** — el campo `word` disparaba el gesto `bloque` (rectángulo dorado que tapa texto). **Fix**: eliminar `word` del prompt y prohibir `bloque` en gestos permitidos.

4. **Nolan narraba progreso a Telegram** — la personalidad no tenía regla explícita de silencio. **Fix**: agregar "Silencio durante producción" en SOUL.md y AGENTS.md + reiniciar Hermes.

5. **Todas las llamadas usaban Sonnet** — Nolan replicaba la lógica de las skills en su turno conversacional en vez de invocar los scripts. **Fix**: sección "EJECUCIÓN — LEER ANTES DEL PROCEDURE" en cada SKILL.md obligando a invocar el script. Además, cambiar modelo base de Hermes de Sonnet a DeepSeek (Sonnet queda solo para copy dentro de scripts).

6. **Variable de token Telegram inconsistente** — `package.py` usaba `HERMES_TELEGRAM_BOT_TOKEN` pero `.env` tenía `TELEGRAM_BOT_TOKEN`. **Fix**: `_bot_base()` lee ambas.

---

## 8. Protocolo para el próximo agente

### Si el usuario dice "continuá con Nolan":

1. **Leer estos archivos en orden** (todos en project root):
   - `HANDOFF.md` (este) — estado y pendientes
   - `SOUL.md` — personalidad Nolan (NO editar sin pedir)
   - `AGENTS.md` — convenciones (NO editar sin pedir)
   - `memory/brand_context.md` — voz de marca

2. **Verificar memoria persistente de Claude Code** (proyecto local, contexto de sesiones previas):
   - `project_nolan_state.md`, `feedback_mateo_workflow.md`

3. **Validar que el VPS responde**:
   ```bash
   ssh <usuario_vps>@<VPS_IP> 'cd /srv/sapiens-nolan && ls skills/nolan-produce-carrusel/scripts/'
   ```

4. **Confirmar con Mateo** qué tarea abordar. Prioridades al 2026-05-18:
   - **Tier 1 (semana del 19 mayo):** skill `nolan-analytics` + extender `rule_writer.py` + dashboard Telegram semanal. Ver `docs/nolan-roadmap-amplificacion.md` §Tier 1.
   - **Tier 5.1:** backup SQLite nocturno (`scripts/backup.sh`).
   - **Fix `produce_guion.py`:** remover emoji/hashtags, integrar EthicsGate.
   - **Voiceover (Q3):** requiere 30 min de reference recording de Mateo primero.

5. **Workflow preferido de Mateo** (ver memoria `feedback_mateo_workflow.md`):
   - Sesiones separadas por fase — no mezclar muchas cosas
   - Paso a paso en el VPS — escribir el comando exacto, esperar resultado antes del siguiente
   - Windows PowerShell sin `ssh-copy-id` — usar `scp` con path completo

### Si el usuario dice "subí X al VPS":

Usar `scp` desde PowerShell con ruta absoluta y IP `<VPS_IP>`:
```powershell
scp "C:\Users\USUARIO\Desktop\Proyectos\nolan-content-agent\<path>" <usuario_vps>@<VPS_IP>:/srv/sapiens-nolan/<path>
```

**NO** uses `\` para continuación de línea en PowerShell (eso es bash). PowerShell usa backtick `` ` `` o una sola línea.

### Si algo genera resultados raros:

- Revisar `logs/llm_usage.jsonl` — confirmar qué modelo se usó para qué task
- Revisar `logs/gateway.log` — mensajes de Hermes
- Si Nolan está narrando progreso o usando modelo incorrecto: reiniciar `hermes-gateway` y verificar que SOUL.md/AGENTS.md están actualizados en `~/.hermes/`

---

## 9. Referencias externas

- Brand kit Sapiens: `c:\Users\USUARIO\Desktop\Proyectos\ai agency\Sapiens_Brand_Kit\` (NO editar desde Nolan)
- Landing Sapiens: `c:\Users\USUARIO\Desktop\Proyectos\ai agency\sapiens-landing\`
- GTM Sapiens: `c:\Users\USUARIO\Desktop\Proyectos\ai agency\Sapiens_GTM\`
- Proyecto Instagram Content: `c:\Users\USUARIO\Desktop\Proyectos\Instagram Content Sapiens\`

Instagram handle: **@sapiens.ed**
Timezone: **America/Bogota (UTC-5)**
