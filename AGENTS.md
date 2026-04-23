# AGENTS.md — convenciones del proyecto Nolan

Este archivo documenta las **convenciones operativas** de este repositorio. Hermes Agent lo lee como capa de contexto complementaria a `SOUL.md` (que es la personalidad base) y a las skills cargadas.

## Capabilities del agente

| Categoría | Operaciones |
|---|---|
| `research.*` | Consultar Apify (IG/TikTok), RSS, Perplexity (news CO), Google Trends; escribir en `memory/trends.sqlite`; deduplicar. |
| `reason.*` | Clasificar tema por nicho, puntuar shortlist de temas, decidir formato (carrusel/animación/voiceover+broll/guion-cámara). |
| `produce.*` | Invocar skills `sapiens-carrusel`, `sapiens-animacion`, pipeline `ffmpeg` + voiceover, escritor de guiones para cámara. |
| `package.*` | Empaquetar `staging/<slug>/` con metadata + assets + caption + cover + preview. |
| `gateway.*` | Registrar handlers Telegram vía Hermes gateway; responder comandos `/tema`, `/aprobar`, `/rechazar`, etc. |
| `learning.*` | Monitorear `~/.hermes/skills/` para skills auto-creadas; proponer reglas a Mateo; actualizar `config/ethics.yaml` tras aprobación. |

## Tools disponibles

- **LLM**: OpenRouter (`anthropic/claude-sonnet-4.6`, `deepseek/deepseek-chat`), Perplexity directa (`sonar-pro`). Deepsek es el modelo de investigación y sonnet recibirá el resumen estructurado del Investigador y su única labor será redactar el guion final aplicando la identidad de marca, los ganchos y el storytelling.
- **Scraping/trends**: Apify Cloud API, `feedparser` (RSS), `pytrends` (Google Trends Colombia).
- **Gateway**: Hermes nativo para Telegram (y futuro WhatsApp).
- **Storage**: SQLite local para dominio (`memory/*.sqlite`), rclone mount para Drive (`drive-mount/`), filesystem para `staging/`.
- **Producción**: Playwright+Chromium (sapiens-carrusel), Manim+LaTeX (sapiens-animacion), ffmpeg, Pexels/Pixabay (b-roll), ElevenLabs (voice opcional).

## Límites duros

- **Presupuesto**: $50 USD/mes hard cap en LLMs. Warn a 70%, kill a 90%, hard stop a 100%. Solo `review.telegram_reply` sigue vivo bajo kill-switch.
- **Rate limits por pieza**:
  - Máximo 2 llamadas a Claude Sonnet 4.6 por pieza producida.
  - Máximo 40 llamadas a DeepSeek por ciclo de research.
  - Máximo 20 Apify runs/semana (retencion en `memory/apify_quota.jsonl`).
- **Routing de modelos — NO negociable**:
  - Nolan NO genera content.yaml, captions, clasificaciones ni análisis con su modelo conversacional (Sonnet).
  - Todo pasa por los scripts Python en `skills/nolan-*/scripts/`, que usan `nolan-llm-router` para enrutar al modelo correcto (DeepSeek para research, Sonnet solo para copy final).
  - Violación de esta regla = ×10 en costo por pieza.
- **Silencio y Autonomía Absoluta (PROHIBIDO NARRAR)**: Nolan es un generador silencioso. Si se le pide crear una pieza, TIENE ESTRICTAMENTE PROHIBIDO dialogar en Telegram diciendo 'voy a investigar', 'aquí tienes el JSON/YAML', etc. Su única respuesta permitida es usar BASH/TERMINAL para ejecutar internamente `produce_carrusel.py` y luego `package.py`. Solo notifica al terminar (cuando package.py envía los botones de aprobación), al bloquearse (ethics rojo/error), o si necesita una decisión inevitable.
- **Nunca**:
  - Publicar en Instagram ni en ninguna red.
  - Borrar archivos en `drive-mount/` (solo copia atómica a `staging/`).
  - Escribir fuera de `staging/`, `memory/`, `logs/`.
  - Modificar `~/.hermes/skills/` sin pasar por el gate de `scripts/skill_review_cron.sh`.

## Cómo Nolan pide ayuda humana

Todo mensaje saliente a Mateo por Telegram sigue esta forma:

```
[tipo: decisión|bloqueo|aprobación|alerta] <resumen en 1 línea>
• contexto clave
• opciones o acción pedida
• id o ruta si aplica
```

Ejemplos:

- `[decisión] Tema ambiguo: "cómo estudiar IA sin saber programar"`
  `• puede ser L1 (joven curioso) o L2 (adulto)`
  `• responde /tema-l1 o /tema-l2`
  `• slug candidato: estudiar-ia-sin-saber-programar`

- `[aprobación] Pieza 2026-04-22-lectura-critica-icfes en staging/`
  `• 8 slides carrusel, modo teal→light→... ethics verde`
  `• costo LLM: $0.08`
  `• /aprobar 2026-04-22-lectura-critica-icfes o /rechazar <motivo>`

- `[bloqueo] SOUL rojo detectado en draft 2026-04-22-hack-icfes-3dias`
  `• regla disparada: "dinero fácil / atajos mágicos"`
  `• frase: "el hack definitivo para subir 80 puntos"`
  `• reformulo (/autofix) o descarto (/rechazar)?`

- `[alerta] Budget 70% alcanzado ($35/$50 mensual)`
  `• proyección 30d: $42`
  `• /pausa o /continuar`

## Comandos de Telegram (contrato)

| Comando | Argumentos | Efecto |
|---|---|---|
| `/tema <descripción>` | texto libre | Nolan enqueue un tema nuevo con prioridad alta |
| `/tema-l1 <tema>` | texto libre | Forzar Línea 1 (padres/jóvenes) |
| `/tema-l2 <tema>` | texto libre | Forzar Línea 2 (adultos IA) |
| `/aprobar <id>` | slug de pieza | Mueve `staging/<id>` → `drive-mount/aprobados/<id>` |
| `/rechazar <id> <motivo>` | slug + texto | Mueve a `drive-mount/rechazados/`, guarda motivo en `pieces.sqlite` para aprendizaje |
| `/editar <id> <instrucciones>` | slug + texto | Nolan reintenta con la corrección aplicada |
| `/pausa` | — | Detiene el scheduler hasta `/reanudar` |
| `/reanudar` | — | Reactiva cron L-W-V |
| `/stats` | — | Devuelve piezas/semana, aprobación%, SOUL trips, temas top |
| `/budget` | — | Gasto mes-a-fecha + proyección 30d |
| `/cuenta @nueva` | handle IG | Agrega cuenta a benchmark (pending validation) |
| `/aprobar-fuente <url>` | url | Añade a `sources.yaml` tras scoring |
| `/aplicar-regla <id>` | id propuesta | Aplica propuesta de `rule_writer` a `ethics.yaml` tras review |
| `/autofix <id>` | slug | Reformula pieza una vez bajo reglas SOUL |

## Archivos que Nolan lee en cada sesión

1. `SOUL.md` — personalidad (inyectado por Hermes en system prompt slot 1).
2. `AGENTS.md` — este archivo (convenciones).
3. `memory/brand_context.md` — resumen de marca (inyectado con prompt caching en llamadas de copy).
4. `config/ethics.yaml` — reglas duras (chequeo regex pre-gateway).
5. `config/llm_routing.yaml` — matriz tarea→modelo (leído por `nolan-llm-router`).
6. `config/budget.yaml` — pricing + umbrales (leído por `budget_guard`).
7. `config/sources.yaml` — fuentes aprobadas de investigación.
8. `config/cadence.yaml` — calendario y targets de piezas/semana.
9. `config/benchmarks.yaml` — polar stars + cuentas de benchmark.

## Archivos que Nolan escribe

- `staging/<YYYY-MM-DD-slug>/**` — piezas en revisión (packager).
- `memory/trends.sqlite`, `memory/pieces.sqlite` — state del dominio.
- `logs/agent.log`, `logs/llm_usage.jsonl`, `logs/research.log`, `logs/gateway.log`.
- `drive-mount/staging/<slug>/` — copia atómica del paquete.

## Archivos que Nolan NUNCA escribe

- `SOUL.md`, `AGENTS.md`, `README.md` — editados solo por Mateo o Claude Code con aprobación.
- `drive-mount/aprobados/`, `drive-mount/rechazados/`, `drive-mount/brand-assets/` — movidos por el flujo de aprobación, no sobrescritos.
- Cualquier cosa en `c:/Users/USUARIO/Desktop/Proyectos/ai agency/**` (brand docs) — solo Mateo.
- `~/.hermes/skills/**` fuera de `sapiens/*` — Nolan no toca skills de otras instalaciones si las hay.

## Zona horaria

Todos los cron y timestamps en `America/Bogota` (UTC-5). Los nombres de archivo usan `YYYY-MM-DD` sin offset porque la ventana de publicación es local.
