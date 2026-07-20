# Nolan — Agente de contenido Sapiens

**Repositorio oficial:** https://github.com/mateo-ortega/nolan-content-agent

**Fuente de verdad** del agente de IA autónomo que produce contenido para Instagram `@sapiens.ed` bajo la identidad Sapiens by Shift.

**Míralo en producción:** [@sapiens.ed en Instagram](https://www.instagram.com/sapiens.ed/) todo el contenido de esa cuenta (carruseles, animaciones, reels) lo produce este agente, sin edición humana previa a la revisión de aprobación.

> Este repositorio es público y sirve como referencia de arquitectura. Los datos de negocio reales (pricing, competencia, playbook de copy exacto, credenciales, infraestructura) están reemplazados por placeholders y ejemplos genéricos — ver [Cómo adaptarlo a tu marca](#cómo-adaptarlo-a-tu-marca).

Este directorio es el **source tree**. Se despliega a un VPS como `/srv/sapiens-nolan/` y puebla `~/.hermes/` del usuario de servicio.

## Qué es Nolan

- Productor de contenido para IG `@sapiens.ed` (carruseles, reels Manim, voiceover+b-roll, guiones para cámara).
- Investiga tendencias de educación e IA, decide formato, produce la pieza y la entrega a Mateo en Google Drive + Telegram para aprobación.
- **Nunca publica directamente.** Human-in-the-loop obligatorio.
- Corre sobre Hermes Agent v0.10+ en VPS con LLMs vía OpenRouter.
- Presupuesto API: $50 USD/mes con kill-switch al 90% (ejemplo real de operación).

## Cómo funciona (pipeline)

```
Cron / Telegram "/tema X"
    │
    ▼
1. research        skills/nolan-research           Apify (IG/TikTok) + RSS + Perplexity + Google Trends
                                                     → shortlist de temas con score, fuentes y ángulo
    ▼
2. decide-format    skills/nolan-decide-format      reglas declarativas + fallback LLM → carrusel | animación | voiceover | talking-head
    ▼
3. produce          skills/nolan-produce-*          escribe copy (DeepSeek research + Claude copy final) y renderiza el asset
                                                     (Playwright para carruseles, Manim+LaTeX para animaciones, ffmpeg para voiceover)
    ▼
4. ethics / alignment gate   sapiens/ethics_gate.py, sapiens/alignment_gate.py
                                                     semáforo verde/amarillo/rojo contra config/ethics.yaml + config/alignment.yaml
                                                     rojo bloquea, amarillo reformula una vez
    ▼
5. package          skills/nolan-package            arma staging/<piece_id>/, sube a Google Drive vía rclone
    ▼
6. aprobación        Telegram (Hermes gateway)       botones /aprobar /rechazar /editar — Nolan nunca publica directo
    ▼
7. learning loop     skills/nolan-learning           analiza rechazos (y aprobaciones) para proponer reglas nuevas a SOUL.md/ethics.yaml
```

Todo el pipeline corre en silencio (sin narrar pasos en el chat) hasta que hay una pieza lista, un bloqueo, o una decisión que requiere a un humano — ver la sección "Silencio de Máquina" en [SOUL.md](SOUL.md).

## Stack

| Capa | Elección |
|---|---|
| Runtime | Hermes Agent (Nous Research) — instancia dedicada |
| LLM gateway | OpenRouter (Claude Sonnet 4.6 + DeepSeek Chat) + Perplexity directa para news |
| Memoria conversacional | Hermes nativa (MEMORY.md + USER.md) + plugin externo (Mem0/Honcho TBD) |
| Memoria de dominio | SQLite local (`memory/trends.sqlite`, `pieces.sqlite`) |
| Gateway revisión | Telegram vía `hermes gateway` (allowlist por env var) |
| Staging | Google Drive vía `rclone` (host, no contenedor) |
| Producción | `sapiens-carrusel` (Playwright), `sapiens-animacion` (Manim+LaTeX), `ffmpeg`, ElevenLabs (opcional) |
| Orquestación | Skills Hermes (`~/.hermes/skills/sapiens/nolan-*/`) |

## Cómo adaptarlo a tu marca

Todo el "conocimiento de marca" vive separado del código, en un puñado de archivos de configuración/prompt. Para reusar Nolan con otra marca no hace falta tocar las skills — solo reescribir esta capa:

| Archivo | Qué controla |
|---|---|
| `SOUL.md` | Identidad del agente: quién eres, tono, funnel/audiencia, prohibiciones duras, cuándo pedir ayuda humana |
| `memory/brand_context.md` | Resumen de marca inyectado (con prompt caching) en cada llamada de copy: identidad, producto, voz, prohibiciones, polar stars editoriales |
| `config/alignment.yaml` | Cuotas de contenido por pillar, arquetipos válidos por formato, vocabulario resonante/de distancia por nicho |
| `config/brand_phase.yaml` | Qué pillars de contenido están permitidos según la fase del negocio (cold start vs escala) |
| `config/ethics.yaml` | Reglas duras del semáforo: regex de promesas absolutas, FOMO, ataque a competencia, política/religión |
| `config/benchmarks.yaml` | Polar stars editoriales (cuentas de referencia) y anti-patterns a evitar |
| `config/sources.yaml` | Fuentes de investigación: cuentas IG/TikTok a monitorear, feeds RSS, queries de Perplexity, Google Trends |
| `config/cadence.yaml` | Piezas/semana objetivo, mix de formatos y nichos, horarios de scheduler |
| `prompts/niches/*.md` | Perfil de lector, cómo hablarle, frases que resuenan/alejan, hooks por audiencia (un archivo por nicho) |
| `prompts/formats/*.md` | Anatomía de cada formato (carrusel, animación, talking-head, voiceover) — estructura de slides/beats |

En este repo esos archivos están rellenos con **placeholders y ejemplos genéricos** en vez de los datos reales de Sapiens (pricing, competencia nombrada, playbook de copy exacto) — son el punto de partida para tu propia marca, no la configuración en producción.

Los tres cambios mínimos para adaptarlo:
1. **Identidad y voz** — reescribe `SOUL.md` y `memory/brand_context.md` con tu marca, producto y tono.
2. **Audiencia** — reemplaza `prompts/niches/*.md` por tus segmentos reales.
3. **Guardrails** — ajusta `config/ethics.yaml` (competencia, promesas prohibidas) y `config/alignment.yaml` (vocabulario de marca) a tu contexto.

## Layout

```
.
├── README.md                  ← este archivo
├── SOUL.md                    ← identidad de Nolan (→ ~/.hermes/SOUL.md en deploy)
├── AGENTS.md                  ← convenciones del proyecto (Hermes las lee)
├── hermes/
│   ├── config.yaml.template   ← copia → ~/.hermes/config.yaml
│   └── .env.example           ← env vars (no commit del .env real)
├── skills/                    ← bundle de skills (→ ~/.hermes/skills/sapiens/*)
│   ├── nolan-research/
│   ├── nolan-decide-format/
│   ├── nolan-produce-carrusel/
│   ├── nolan-produce-animacion/
│   ├── nolan-produce-voiceover/
│   ├── nolan-package/
│   └── nolan-llm-router/
├── config/                    ← configuración leída por las skills
│   ├── llm_routing.yaml
│   ├── budget.yaml
│   ├── ethics.yaml
│   ├── cadence.yaml
│   ├── sources.yaml
│   └── benchmarks.yaml
├── memory/
│   ├── brand_context.md       ← se inyecta al top del prompt de copy
│   └── schemas/               ← DDL de las SQLite de dominio
├── prompts/
│   ├── system/                ← investigator, strategist, copywriter, source_validator
│   ├── niches/                ← padres, jovenes_preicfes, adultos_ia, pymes
│   └── formats/               ← talking_head, voiceover_broll, carrusel, animacion
├── scripts/
│   ├── bootstrap_vps.sh       ← provisioning Ubuntu 24.04
│   ├── install_sapiens_fonts.sh
│   ├── smoke_tests.sh
│   ├── skill_review_cron.sh   ← gate de aprobación humana de auto-skills
│   └── backup.sh
├── docs/
│   ├── hermes-architecture-notes.md   ← decisiones de arquitectura sobre Hermes Agent
│   ├── nolan-roadmap-amplificacion.md ← roadmap técnico priorizado por leverage
│   └── infra-estado-2026-06-06.md     ← estado operativo de la instancia VPS
├── staging/                   ← outputs antes de Drive (gitignored)
└── logs/                      ← agent.log, llm_usage.jsonl (gitignored)
```



Ver `docs/infra-estado-2026-06-06.md` para el detalle operativo actual.

## Referencias

- Hermes docs: https://hermes-agent.nousresearch.com/docs
- Hermes repo: https://github.com/NousResearch/hermes-agent
- Documentos de marca, GTM y pricing reales de Sapiens: privados, no versionados en este repo.
