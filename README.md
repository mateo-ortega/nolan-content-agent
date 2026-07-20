# Nolan — Agente de contenido Sapiens

**Repositorio oficial:** https://github.com/mateo-ortega/nolan-content-agent

**Fuente de verdad** del agente de IA autónomo que produce contenido para Instagram `@sapiens.ed` bajo la identidad Sapiens by Shift.

Este directorio es el **source tree**. Se despliega al VPS Hostinger como `/srv/sapiens-nolan/` y puebla `~/.hermes/` del usuario de servicio.

## Qué es Nolan

- Productor de contenido para IG `@sapiens.ed` (carruseles, reels Manim, voiceover+b-roll, guiones para cámara).
- Investiga tendencias de educación e IA, decide formato, produce la pieza y la entrega a Mateo en Google Drive + Telegram para aprobación.
- **Nunca publica directamente.** Human-in-the-loop obligatorio.
- Corre sobre Hermes Agent v0.10+ en VPS Hostinger con LLMs vía OpenRouter.
- Presupuesto API: $50 USD/mes con kill-switch al 90%.

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
│   └── hermes-architecture-notes.md
├── staging/                   ← outputs antes de Drive (gitignored)
└── logs/                      ← agent.log, llm_usage.jsonl (gitignored)
```

## Status (abril 2026)

- [x] Fase 0 — brand docs actualizados, Hermes validado, scaffold local
- [ ] Fase 1 — provisioning VPS Hostinger + Hermes `hello-world`
- [ ] Fase 2 — porteo skills + smoke (carrusel PNG + Manim MP4)
- [ ] Fase 3 — skills Nolan + router LLM + Gateway Telegram + rclone
- [ ] Fase 4 — dry-run end-to-end con tema hardcoded
- [ ] Fase 5 — go-live con cadencia mínima 3/sem
- [ ] Fase 6 — learning loop + escalado + WhatsApp

## Referencias

- Plan maestro: `C:\Users\USUARIO\.claude\plans\contexto-inicial-para-claude-groovy-hejlsberg.md`
- Brand identity: `c:\Users\USUARIO\Desktop\Proyectos\ai agency\SAPIENS_BRAND_IDENTITY.md`
- Brand profile: `c:\Users\USUARIO\Desktop\Proyectos\ai agency\Sapiens_GTM\brand-profile.json`
- Paquetes/precios: `c:\Users\USUARIO\Desktop\Proyectos\ai agency\Sapiens_GTM\paquetes_y_precios.md`  "estos precios son solo para tener una idea de lo que se puede ofrecer"
- Hermes docs: https://hermes-agent.nousresearch.com/docs
- Hermes repo: https://github.com/NousResearch/hermes-agent
