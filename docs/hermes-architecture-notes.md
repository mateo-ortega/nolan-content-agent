# Hermes Agent v0.10 — notas de arquitectura (Nolan)

> **Estado**: validado en fase 0 (2026-04-19) contra docs oficiales `hermes-agent.nousresearch.com/docs`.
> **Propósito**: documentar las diferencias entre lo asumido al diseñar y lo que Hermes realmente ofrece, para que fases 1–3 no arrastren supuestos rotos.

---

## 1. Hermes es **single-agent por instancia**

La idea original de "multi-agente con `agents/<name>/`" no aplica. Hermes corre como un solo agente con su identidad en `~/.hermes/SOUL.md` y su config en `~/.hermes/config.yaml` (o `$HERMES_HOME/config.yaml`).

**Qué significa para Nolan**:
- "Nolan" = **identidad (SOUL.md) + bundle de skills + config**, todo viviendo en una instancia Hermes dedicada a Sapiens.
- Si mañana queremos un segundo agente (ej. "Lira" para fragancias), será otra instancia Hermes corriendo en paralelo — probablemente en otro usuario Linux o contenedor, con su propio `HERMES_HOME`.
- No hay "directorio por agente" en Hermes; lo que estamos llamando `/srv/sapiens-nolan/` es el **source tree** del proyecto que se despliega a `~/.hermes/*` + mount points.

## 2. Archivos de contexto reales

| Archivo | Ubicación real | Qué contiene | Slot en system prompt |
|---|---|---|---|
| `SOUL.md` | `~/.hermes/SOUL.md` | Identidad + valores + prohibiciones duras | #1 (siempre al tope) |
| `AGENTS.md` | `$PWD/AGENTS.md` (convenciones del repo) | Capabilities, herramientas, límites, formato de mensajes | #2 (contexto del proyecto) |
| `MEMORY.md` | `~/.hermes/memories/MEMORY.md` | Memoria global de Hermes (máx 2200 chars) | #3 |
| `USER.md` | `~/.hermes/memories/USER.md` | Perfil del usuario principal (máx 1375 chars) | #4 |

**IDENTITY.md no es nativo**. Lo fusionamos en el encabezado de `SOUL.md` (bloque "Identidad" al tope).

## 3. Skills: formato Claude-compatible

Hermes implementa exactamente el schema de Claude skills:

```
~/.hermes/skills/<category>/<skill-name>/
├── SKILL.md          (YAML frontmatter + markdown)
└── scripts/          (opcional, Python/bash referenciados desde SKILL.md)
```

**Frontmatter obligatorio** para que Hermes las cargue:
```yaml
---
name: <slug>
description: <1 línea para matcher>
version: <semver>
platforms: [linux]
metadata:
  hermes:
    tags: [<...>]
    category: <category>
    requires_toolsets: [terminal, llm, http]
---
```

Nolan tendrá 7 skills bajo categoría `sapiens`:
- `nolan-research`
- `nolan-decide-format`
- `nolan-produce-carrusel` (wrapper sobre skill legacy)
- `nolan-produce-animacion` (wrapper sobre skill legacy)
- `nolan-produce-voiceover`
- `nolan-package`
- `nolan-llm-router` (librería, no conversacional)

Más 2 skills legacy portadas bajo categoría `sapiens-legacy`:
- `sapiens-carrusel`
- `sapiens-animacion`

## 4. Memoria: nativa pequeña + plugins + dominio propio

**Nativa** (Hermes):
- `MEMORY.md` 2200 chars — hechos globales compartidos entre sesiones
- `USER.md` 1375 chars — perfil del usuario (Mateo)

**Plugins externos** (decidir fase 0): Honcho, Mem0, OpenViking, Hindsight, Holographic, RetainDB, ByteRover, Supermemory.

**Recomendación para Nolan**: **Mem0** para memoria conversacional extendida (contexto de piezas pasadas, preferencias editoriales aprendidas). Honcho es alternativa viable; decisión final al integrar.

**Dominio denso** (nuestro, no de Hermes):
- `memory/trends.sqlite` — signals de research, append-only, hash-indexado
- `memory/pieces.sqlite` — registro de piezas producidas, estado, costos
- `memory/brand_context.md` — 2 páginas cargadas vía prompt caching en cada copy

## 5. Gateway Telegram: setup wizard nativo

El Gateway existe out-of-the-box. Setup:

```bash
hermes gateway setup    # wizard interactivo
# pide: bot token, allowed user IDs, canales (Telegram/WhatsApp/Discord según build)
```

Allowlist por env:
- `TELEGRAM_ALLOWED_USERS=<id1>,<id2>` o `GATEWAY_ALLOWED_USERS=<...>`

Pairing por DM: usuario desconocido manda `/start` → Hermes genera código one-time → Mateo aprueba con `hermes pairing approve <code>`.

**No necesitamos `python-telegram-bot` como implementación principal**. Queda como plan B si el Gateway Hermes tiene gap específico (ej. media groups con botones inline avanzados). Confirmar en fase 3.

## 6. Per-task LLM routing: NO nativo

Hermes corre con **un modelo principal** configurado en `config.yaml` (`model: openrouter/claude-sonnet-4.6`). No soporta tabla `tasks → models` arbitraria.

**Nuestra solución**: `nolan-llm-router` es **librería Python** empaquetada como skill. Cuando `nolan-research` ejecuta, importa la librería y llama DeepSeek directamente vía OpenRouter. Cuando `nolan-produce-carrusel` llama Claude Sonnet para copy, usa la misma librería. Hermes nunca se entera.

**Implicación**: los "costos LLM" en `logs/llm_usage.jsonl` son de **nuestras skills**, no del turno conversacional de Hermes con Mateo. El budget guard cubre nuestras llamadas; el uso conversacional de Hermes con Mateo es mínimo (pocos turnos, caché caliente) y lo estimamos en < $3/mes dentro del budget global.

## 7. Auto-learning: sin gate humano nativo

Hermes auto-crea skills tras:
- 5+ tool calls exitosos al mismo patrón
- Errores resueltos por el agente
- Correcciones explícitas del usuario

**No hay aprobación humana incorporada** antes de persistir la skill.

**Nuestro gate custom** (`scripts/skill_review_cron.sh`):
1. Cron diario 23:00 Bogotá.
2. Diff de `~/.hermes/skills/` contra snapshot `memory/skills-snapshot.json` del día anterior.
3. Skills nuevas o modificadas → copiar a `staging/skills-review/<date>/` + notificar Telegram con resumen.
4. Mateo aprueba con `/aplicar-regla <skill-name>` (mueve a `~/.hermes/skills/sapiens-auto/`) o `/rechazar-regla <skill-name>` (elimina).
5. Actualizar snapshot tras la decisión.

## 8. Triggers (cron, webhook): systemd + CLI

No hay sección `triggers` nativa en `config.yaml`. Usamos:

- **Cron L-W-V 06:00** (research ciclo):
  ```
  systemd-timer research.timer → research.service → hermes chat "ejecuta research.ciclo_lwf"
  ```
- **Webhook externo** (futuro): binario pequeño en `scripts/webhook_bridge.py` escuchando en `127.0.0.1:9090`, traduce POST a `hermes chat <cmd>` y responde 200.
- **Gateway Telegram**: invocado por el Gateway Hermes cuando Mateo manda `/tema`, `/aprobar`, etc. No necesita cron.

## 9. Prompt caching con Anthropic via OpenRouter

OpenRouter pasa `cache_control: {type: "ephemeral"}` al provider Anthropic cuando el cliente lo emite en bloques `system`. Esto se maneja en **nuestro** `openrouter_client.py` dentro de `nolan-llm-router`, no en Hermes.

Bloques a cachear (cacheables entre calls si son idénticos byte-a-byte durante 5 min):
1. `SOUL.md` completo (~6 KB)
2. `memory/brand_context.md` (~5 KB)
3. Prompt de sistema de la skill de copy (`prompts/system/copywriter.md`)
4. Benchmark fixture (`prompts/formats/<format>.md`)

Total system prompt cacheado: ~20–25 KB. Ahorro esperado: ~90% en tokens input de copy (de $3/Mtok a $0.30/Mtok).

## 10. Qué se descartó del plan original

- `hermes.yaml` por agente → reemplazado por `config.yaml` global.
- `src/main.py + react_loop.py` custom → **no existe**. El react loop es intrínseco de Hermes; nuestra lógica vive en skills.
- `agents/nolan/*` como raíz → pasa a ser source tree en Windows; despliegue a `~/.hermes/*` en VPS.
- `per-task triggers` en yaml → systemd + Gateway + webhooks custom.
- `auto_learning.approval_required` como flag nativo → reemplazado por cron de review.

## 11. Qué se mantuvo sin cambios

- OpenRouter como gateway LLM único.
- Perplexity directa (no OpenRouter) para noticias con citaciones.
- rclone en host (fuera de Docker) para Google Drive.
- Prompt caching Anthropic via OpenRouter.
- Pipeline de 6 etapas (research → reason → ethics → decide → produce → package).
- SOUL semáforo, ethics regex, budget guard, circuit breaker.
- Skills legacy `sapiens-carrusel` y `sapiens-animacion` portadas tal cual.

## 12. Decisiones pendientes fase 1

- [ ] Versión exacta de Hermes a instalar (latest vs pinned). Candidato: último release estable al día del install.
- [ ] Plugin de memoria extendida: Mem0 vs Honcho vs ninguno en v1.
- [ ] Si el Gateway Hermes soporta media groups con inline buttons (para preview carrusel). Si no, fallback `python-telegram-bot` parcial.
- [ ] Slugs OpenRouter vigentes al día del deploy (`anthropic/claude-sonnet-4.6` vs alternativos — confirmar en `curl $OPENROUTER_BASE_URL/models`).
- [ ] Confirmar que `hermes install` trae los toolsets `terminal`, `llm`, `http` que las skills declaran en `requires_toolsets`.
