# Estado de infraestructura — Nolan

> Documento de referencia rápida sobre el estado operativo de Nolan. Actualizar en cada hito significativo.

## Infraestructura VPS

| Item | Valor |
|---|---|
| Proveedor | Hostinger KVM 2 |
| IP | `<VPS_IP>` |
| OS | Ubuntu 24.04 LTS |
| Usuario | `<usuario_vps>` (sudo) |
| Proyecto | `/srv/sapiens-nolan/` |
| Venv | `/srv/nolan-venv/` (Python 3.12.3) |
| Stack | FFmpeg 6.1.1, Manim 0.20.1, Playwright+Chromium, LuaLaTeX, rclone, SQLite, Docker |
| Hermes | `~/.local/bin/hermes`, modelo base DeepSeek via OpenRouter |
| Systemd | `hermes-gateway.service` (enabled, running) |

## Formatos de producción

| Formato | Estado | Script |
|---|---|---|
| Carrusel v1 (Playwright+Jinja) | Operativo | `produce_carrusel.py` |
| Carrusel DS (HTML magazine) | Operativo | `produce_carrusel_ds.py` |
| Animación Manim | Operativo | `produce_animacion.py` |
| Guion talking-head | Operativo con bugs menores | `produce_guion.py` |
| Voiceover + B-roll | Stub solamente | Bloqueado: reference recording + ElevenLabs |

## Routing de modelos (no negociable)

- Research / clasificación: DeepSeek v4 Flash vía NVIDIA NIM (gratuito, 40 RPM) + fallback OpenRouter
- Copy final: Claude Sonnet vía OpenRouter
- Web search con citaciones: Perplexity sonar-pro directo

## Costo actual

Ejemplo real de operación: ~$7 USD/mes. Cap configurado en `config/budget.yaml`: $50 USD/mes.

## Pendientes prioritarios

| Item | Prioridad | Esfuerzo |
|---|---|---|
| `nolan-analytics` (métricas IG diarias) | Alta | S |
| Learning loop positivo + negativo | Alta | S |
| Dashboard semanal Telegram | Alta | S |
| Fix `produce_guion.py` (emoji, hashtags, EthicsGate) | Media | 2h |
| Backup SQLite nocturno (`scripts/backup.sh`) | Media | S |
