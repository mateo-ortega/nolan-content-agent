---
name: nolan-learning
description: Learning loop de Nolan. Analiza patrones de rechazo en pieces.sqlite y propone reglas concretas para SOUL.md via DeepSeek. También detecta skills auto-creadas por Hermes para revisión. Ejecutado semanalmente por hermes cron.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [learning, soul, rules, feedback, sapiens, nolan]
    category: sapiens
    requires_toolsets: [llm, terminal, http]
---

# nolan-learning

Cierra el loop de aprendizaje autónomo de Nolan.

## Scripts

| Script | Propósito |
|--------|-----------|
| `rule_writer.py` | Analiza rechazos → identifica patrones → propone reglas por Telegram |
| `apply_rule.py`  | Aplica o rechaza una propuesta al recibir callback de Mateo |

## Flujo

```
rechazos en pieces.sqlite (últimos 90 días)
    │
    ▼
rule_writer.py  ──►  DeepSeek cluster
    │
    ▼  (≥3 rechazos del mismo patrón)
rule_proposals table
    │
    ▼
Telegram: "Propuesta #N: [patrón]. [Aplicar] [Rechazar]"
    │
    ▼  (Mateo toca "Aplicar")
apply_rule.py  ──►  SOUL.md actualizado  ──►  Hermes reiniciado
```

## Cron

Ejecutado cada domingo a las 18:00 Bogotá (23:00 UTC) por hermes cron.
