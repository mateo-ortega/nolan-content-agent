---
name: nolan-llm-router
description: Router + budget guard + cliente OpenRouter para todas las llamadas LLM de las skills nolan-*. Lee config/llm_routing.yaml, aplica prompt caching Anthropic cuando corresponda, registra uso en logs/llm_usage.jsonl, y dispara kill-switch al 90% del budget mensual. Invocado como librería Python por las otras skills nolan.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [llm, router, budget, openrouter, sapiens, nolan]
    category: sapiens
    requires_toolsets: [llm, http]
---

# nolan-llm-router

No es una skill conversacional — es una **librería Python** empaquetada como skill para que las demás skills `nolan-*` la importen. Hermes no tiene routing nativo por tarea; nosotros lo añadimos.

## When to use

Cualquier skill `nolan-*` que necesite invocar un LLM con modelo específico (DeepSeek para research, Claude Sonnet para copy, Perplexity para news). **No lo usa Hermes para su turno conversacional** — Hermes sigue con su modelo principal configurado en `~/.hermes/config.yaml`.

## API (import desde otras skills)

```python
from sapiens.nolan_llm_router import LLMRouter, load_router
router = load_router()  # carga config/llm_routing.yaml + config/budget.yaml

resp = router.call(
    task="copy.final_caption",
    messages=[{"role": "system", "content": SOUL_MD + BRAND_CONTEXT_MD},
              {"role": "user",   "content": brief_yaml}],
    cache_system=True,   # prompt caching Anthropic ephemeral
)
# resp.text, resp.usage, resp.cost_usd, resp.model_used
```

## Procedure interna (por llamada)

1. **Resolver spec** — `routing.tasks[task]` → `{provider, model, max_tokens, cache}`.
2. **Preflight budget** (`budget_guard.preflight`):
   - Lee `logs/llm_usage.jsonl` del mes corriente.
   - Estima `expected_cost_usd` con pricing de `config/budget.yaml`.
   - Si `mes_actual + expected > BUDGET_KILL_THRESHOLD × LLM_MONTHLY_BUDGET_USD` y `task` no está en whitelist crítica (`review.*`) → **abort con `BudgetKillError`**.
   - Si `> WARN` y la alerta del mes aún no se envió → dispatch notify Telegram.
3. **Armar request**:
   - Provider `openrouter`: OpenAI-compatible client a `OPENROUTER_BASE_URL` con headers `Authorization`, `HTTP-Referer`, `X-Title`.
   - Provider `perplexity`: cliente propio a `api.perplexity.ai` con `return_citations=true`, `search_recency_filter=week`.
   - Si `cache: true` y modelo es `anthropic/*`: marcar bloques system con `cache_control: {type: "ephemeral"}`.
4. **Circuit breaker**:
   - Contador por provider: 3 errores 5xx consecutivos → pausa 30 min.
   - Si OpenRouter caído para `anthropic/*`, degradar a `anthropic/claude-sonnet-4` (fallback definido en `llm_routing.yaml`) y flag en metadata.
5. **Retry** con backoff exponencial (1s, 2s, 4s) para errores `429` y `503`. Max 3 intentos.
6. **Registrar uso** en `logs/llm_usage.jsonl`:
   ```json
   {"ts":"2026-04-22T14:10:33-05:00","task":"copy.final_caption",
    "provider":"openrouter","model":"anthropic/claude-sonnet-4.6",
    "in_tok":3420,"out_tok":320,"cached_tok":2800,"cost_usd":0.0046,
    "latency_ms":4210,"piece_id":"2026-04-22-..."}
   ```
7. **Devolver** `LLMResponse` con `text`, `usage`, `cost_usd`, `citations` (si Perplexity), `model_used`.

## Pricing table (`config/budget.yaml`)

Referencia actual (actualizar 1×/mes ejecutando `scripts/refresh_pricing.py`):

| Modelo | Input $/Mtok | Output $/Mtok | Cache read |
|---|---|---|---|
| `anthropic/claude-sonnet-4.6` | 3.00 | 15.00 | 0.30 |
| `deepseek/deepseek-chat` | 0.27 | 1.10 | — |
| `perplexity/sonar-pro` (directa) | 3.00 in + $5/1k búsquedas | — | — |

**OpenRouter markup**: ~5% encima del precio del provider — incluido en el total reportado.

## Pitfalls

- **Prompt caching cache miss**: Anthropic invalida cache si cambia 1 byte del bloque cacheado. Mantener `SOUL.md` + `brand_context.md` estables durante la semana; si cambian, aceptar 1 día de miss.
- **Token counting inconsistente**: OpenRouter reporta `usage` pero no siempre separa `cached_prompt_tokens`. Si falta, asumir 0 cache y corregir con `/calibrate-pricing` mensual comparando contra facturación real.
- **Perplexity citations vacías**: si `citations: []`, la skill de research debe descartar la señal o marcarla `low_confidence`. No es responsabilidad del router; el router solo pasa el payload.
- **Budget guard race condition**: dos skills llamando en paralelo pueden ambas pasar preflight justo por debajo del umbral. Usar lock en `logs/llm_usage.lock` con `fcntl.flock` Linux (ok al portarlo solo a VPS).
- **Mes nuevo**: `logs/llm_usage.jsonl` no se trunca; budget_guard filtra por timestamp del mes corriente UTC-5 (Bogotá).

## Verification

```bash
# Test unitario: llamada mock sin consumir budget
py -3.12 -m sapiens.nolan_llm_router.tests.smoke

# Test real: 1 llamada barata a DeepSeek
hermes chat "llm_router_cli --task research.classify_niche --input '{\"text\":\"ICFES Saber 11 2026\"}'"
# Esperado: response con {niche: 'jovenes_preicfes', confidence: >0.8}, cost < $0.002

# Budget status
hermes chat "llm_router_cli --budget-status"
# Esperado: {month:'2026-04', spent_usd:0.38, budget_usd:50, used_pct:0.0076, status:'healthy'}
```

## Outputs

- `logs/llm_usage.jsonl` — append-only
- Retorno `LLMResponse` a la skill que llama
- Alertas Telegram en warn/kill
- `pieces.sqlite.llm_cost_usd` actualizado por piece_id
