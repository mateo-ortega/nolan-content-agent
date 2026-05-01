"""
LLM Router y Budget Guard para Nolan — Sapiens by Shift.

Importar:
    from sapiens.nolan_llm_router import LLMRouter, BudgetGuard, load_router

Carga config/llm_routing.yaml + config/budget.yaml, enruta tareas al modelo
correcto (OpenRouter o Perplexity), aplica prompt caching Anthropic, y registra
uso en logs/llm_usage.jsonl con lock de archivo.
"""

import fcntl
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml

PROJECT_ROOT = Path(os.environ.get("NOLAN_PROJECT_ROOT", Path(__file__).parent.parent))


def _load_env():
    """Carga .env desde ubicaciones conocidas si python-dotenv está instalado."""
    try:
        from dotenv import load_dotenv
        for candidate in [
            PROJECT_ROOT / ".env",
            Path.home() / ".hermes" / ".env",
        ]:
            if candidate.exists():
                load_dotenv(candidate, override=False)
                break
    except ImportError:
        pass


_load_env()


# ---------------------------------------------------------------------------
# Tipos de datos
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    text: str
    model_used: str
    usage: dict
    cost_usd: float
    citations: list = field(default_factory=list)
    cached: bool = False


class BudgetKillError(Exception):
    pass


# ---------------------------------------------------------------------------
# BudgetGuard
# ---------------------------------------------------------------------------

class BudgetGuard:
    """Preflight de presupuesto mensual. Thread-safe vía fcntl.flock."""

    def __init__(self, cfg: dict, usage_log: Path):
        self.cfg = cfg
        self.usage_log = usage_log
        self.usage_log.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = usage_log.with_suffix(".lock")

        self.monthly_budget: float = cfg["monthly_budget_usd"]
        self.warn_t: float = cfg["thresholds"]["warn"]
        self.kill_t: float = cfg["thresholds"]["kill"]
        self.hard_t: float = cfg["thresholds"]["hard"]
        self.pricing: dict = cfg.get("pricing", {})
        self.perp_pricing: dict = cfg.get("perplexity_pricing", {})

    # ------------------------------------------------------------------
    def estimate_cost(self, model: str, max_tokens: int) -> float:
        """Estimación conservadora: asume max_tokens como output."""
        p = self.pricing.get(model) or self.perp_pricing.get(model)
        if not p:
            return 0.01
        out_usd = p.get("output_per_mtok", 15.0) * max_tokens / 1_000_000
        fee = 1 + p.get("openrouter_fee_pct", 0) / 100
        return out_usd * fee

    def compute_actual_cost(self, model: str, usage: dict) -> float:
        p = self.pricing.get(model) or self.perp_pricing.get(model, {})
        if not p:
            return 0.0
        in_tok = usage.get("prompt_tokens", 0) - usage.get("cached_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        cached_tok = usage.get("cached_tokens", 0)
        fee = 1 + p.get("openrouter_fee_pct", 0) / 100
        cost = (
            in_tok * p.get("input_per_mtok", 3.0) / 1_000_000
            + out_tok * p.get("output_per_mtok", 15.0) / 1_000_000
            + cached_tok * p.get("cache_read_per_mtok", 0.30) / 1_000_000
        ) * fee
        return round(cost, 6)

    def month_spent(self) -> float:
        """Suma costo del mes en curso (UTC-5) desde logs/llm_usage.jsonl."""
        if not self.usage_log.exists():
            return 0.0
        cur_month = datetime.now(tz=timezone.utc).astimezone().strftime("%Y-%m")
        total = 0.0
        try:
            with open(self.usage_log, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("ts", "").startswith(cur_month):
                            total += rec.get("cost_usd", 0.0)
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass
        return total

    def preflight(self, task: str, estimated_cost: float):
        spent = self.month_spent()
        ratio = (spent + estimated_cost) / self.monthly_budget

        if ratio >= self.hard_t:
            raise BudgetKillError(
                f"Budget hard stop ({ratio*100:.1f}%). "
                f"Gastado: ${spent:.2f}/${self.monthly_budget:.0f}"
            )
        if ratio >= self.kill_t and not task.startswith("review."):
            raise BudgetKillError(
                f"Budget kill-switch ({ratio*100:.1f}%). "
                f"Solo review.* permitido. Usa /budget para revisar."
            )
        if ratio >= self.warn_t:
            print(
                f"WARN [budget] {self.warn_t*100:.0f}% alcanzado "
                f"(${spent:.2f}/${self.monthly_budget:.0f})",
                file=sys.stderr,
            )

    def record(
        self,
        task: str,
        model: str,
        provider: str,
        usage: dict,
        cost_usd: float,
        piece_id: str = "",
    ):
        """Append-only a logs/llm_usage.jsonl con file lock POSIX."""
        entry = {
            "ts": datetime.now(tz=timezone.utc).astimezone().isoformat(),
            "task": task,
            "provider": provider,
            "model": model,
            "in_tok": usage.get("prompt_tokens", 0),
            "out_tok": usage.get("completion_tokens", 0),
            "cached_tok": usage.get("cached_tokens", 0),
            "cost_usd": cost_usd,
            "piece_id": piece_id,
        }
        with open(self.lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                with open(self.usage_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# LLMRouter
# ---------------------------------------------------------------------------

class LLMRouter:
    """Enruta llamadas LLM según llm_routing.yaml con budget guard y retry."""

    def __init__(self, routing_cfg: dict, guard: BudgetGuard):
        self.routing = routing_cfg
        self.guard = guard
        self._cb: dict[str, int] = {}  # circuit breaker: provider → errores consecutivos

    # ------------------------------------------------------------------
    def call(
        self,
        task: str,
        messages: list,
        cache_system: bool = False,
        piece_id: str = "",
    ) -> LLMResponse:
        spec = self._resolve_spec(task)
        provider = spec.get("provider", self.routing["defaults"]["provider"])
        model = spec["model"]
        max_tokens = spec.get("max_tokens", 1000)
        temperature = spec.get("temperature", self.routing["defaults"].get("temperature", 0.4))

        self.guard.preflight(task, self.guard.estimate_cost(model, max_tokens))

        try:
            if provider == "openrouter":
                resp = self._call_openrouter(model, messages, max_tokens, temperature,
                                             cache_system, spec)
            elif provider == "perplexity":
                resp = self._call_perplexity(model, messages, max_tokens, spec)
            elif provider == "nvidia_nim":
                resp = self._call_nvidia_nim(model, messages, max_tokens, temperature, spec)
            else:
                raise ValueError(f"Provider desconocido: {provider}")
        except RuntimeError as primary_err:
            fb = self._get_provider_fallback(task, provider)
            if fb:
                print(
                    f"[llm-router] {provider} falló para '{task}', "
                    f"usando fallback {fb['provider']}:{fb['model']}",
                    file=sys.stderr,
                )
                if fb["provider"] == "nvidia_nim":
                    resp = self._call_nvidia_nim(fb["model"], messages, max_tokens, temperature, spec)
                elif fb["provider"] == "openrouter":
                    resp = self._call_openrouter(fb["model"], messages, max_tokens, temperature,
                                                 cache_system, spec)
                else:
                    raise primary_err
                provider = fb["provider"]
                model = fb["model"]
            else:
                raise primary_err

        resp.cost_usd = self.guard.compute_actual_cost(model, resp.usage)
        self.guard.record(task, model, provider, resp.usage, resp.cost_usd, piece_id)
        return resp

    def _get_provider_fallback(self, task: str, failed_provider: str) -> Optional[dict]:
        """Devuelve config del fallback de proveedor para la tarea, o None."""
        key = f"{failed_provider}_fallback"
        fb_cfg = self.routing.get(key, {})
        if not fb_cfg:
            return None
        pattern = fb_cfg.get("tasks_pattern", "")
        if pattern and not re.match(pattern, task):
            return None
        # Verificar que el fallback tiene su key de API disponible
        target_provider = fb_cfg.get("provider", "")
        if target_provider == "nvidia_nim" and not os.environ.get("NVIDIA_API_KEY", ""):
            return None
        if target_provider == "openrouter" and not os.environ.get("OPENROUTER_API_KEY", ""):
            return None
        return {"provider": target_provider, "model": fb_cfg["model"]}

    # ------------------------------------------------------------------
    def _resolve_spec(self, task: str) -> dict:
        tasks = self.routing.get("tasks", {})
        if task not in tasks:
            raise ValueError(f"Tarea '{task}' no definida en llm_routing.yaml")
        spec = dict(self.routing.get("defaults", {}))
        spec.update(tasks[task])
        return spec

    def _call_openrouter(
        self, model, messages, max_tokens, temperature, cache_system, spec
    ) -> LLMResponse:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError("Falta OPENROUTER_API_KEY en el entorno")
        base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

        prepared = (
            self._apply_cache_control(messages)
            if cache_system and "anthropic/" in model
            else list(messages)
        )
        payload: dict[str, Any] = {
            "model": model,
            "messages": prepared,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if spec.get("response_format") == "json_object":
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER", "https://sapienseducation.com"),
            "X-Title": os.environ.get("OPENROUTER_X_TITLE", "nolan"),
            "Content-Type": "application/json",
        }
        data = self._post_with_retry(f"{base_url}/chat/completions", headers, payload, "openrouter")

        choice = data["choices"][0]
        usage = data.get("usage", {})
        cached = usage.get("cached_tokens", 0) > 0
        return LLMResponse(
            text=choice["message"]["content"],
            model_used=data.get("model", model),
            usage=usage,
            cost_usd=0.0,
            cached=cached,
        )

    def _call_perplexity(self, model, messages, max_tokens, spec) -> LLMResponse:
        api_key = os.environ.get("PERPLEXITY_API_KEY", "")
        if not api_key:
            raise RuntimeError("Falta PERPLEXITY_API_KEY en el entorno")
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "return_citations": spec.get("return_citations", True),
            "search_recency_filter": spec.get("search_recency_filter", "week"),
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = self._post_with_retry(
            "https://api.perplexity.ai/chat/completions", headers, payload, "perplexity"
        )
        choice = data["choices"][0]
        return LLMResponse(
            text=choice["message"]["content"],
            model_used=model,
            usage=data.get("usage", {}),
            cost_usd=0.0,
            citations=data.get("citations", []),
        )

    def _call_nvidia_nim(
        self, model: str, messages: list, max_tokens: int, temperature: float, spec: dict
    ) -> LLMResponse:
        """NVIDIA NIM — OpenAI-compatible, gratis hasta 1000 req/mes."""
        api_key = os.environ.get("NVIDIA_API_KEY", "")
        if not api_key:
            raise RuntimeError("Falta NVIDIA_API_KEY en el entorno")
        base_url = "https://integrate.api.nvidia.com/v1"
        payload: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if spec.get("response_format") == "json_object":
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # Timeout amplio: NIM free tier es lento con payloads grandes (30-50 señales).
        # Si igualmente falla → fallback a OR vía nvidia_nim_fallback.
        data = self._post_with_retry(
            f"{base_url}/chat/completions", headers, payload, "nvidia_nim", timeout_secs=120
        )
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return LLMResponse(
            text=choice["message"]["content"],
            model_used=data.get("model", model),
            usage=usage,
            cost_usd=0.0,
        )

    def _apply_cache_control(self, messages: list) -> list:
        result = []
        for msg in messages:
            if msg["role"] == "system" and isinstance(msg["content"], str):
                result.append({
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": msg["content"],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                })
            else:
                result.append(msg)
        return result

    def _post_with_retry(
        self, url: str, headers: dict, payload: dict, provider: str,
        timeout_secs: float = 120.0,
    ) -> dict:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=timeout_secs) as client:
                    r = client.post(url, headers=headers, json=payload)

                if r.status_code == 429:
                    wait = float(r.headers.get("retry-after", 2 ** (attempt + 1)))
                    print(f"[llm-router] 429 {provider}, esperar {wait:.0f}s", file=sys.stderr)
                    time.sleep(wait)
                    continue
                elif r.status_code >= 500:
                    self._cb[provider] = self._cb.get(provider, 0) + 1
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                r.raise_for_status()
                self._cb[provider] = 0
                return r.json()

            except httpx.TimeoutException:
                print(f"[llm-router] timeout {provider} intento {attempt+1}/{max_retries}", file=sys.stderr)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                # Convierte a RuntimeError para que el fallback de proveedor lo capture
                raise RuntimeError(f"Timeout agotado ({max_retries} intentos) para {provider}")

        raise RuntimeError(f"Agotados {max_retries} intentos para {provider}")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def load_router() -> LLMRouter:
    """Carga LLMRouter desde config/*.yaml del proyecto."""
    root = PROJECT_ROOT
    with open(root / "config" / "llm_routing.yaml", encoding="utf-8") as f:
        routing_cfg = yaml.safe_load(f)
    with open(root / "config" / "budget.yaml", encoding="utf-8") as f:
        budget_cfg = yaml.safe_load(f)
    guard = BudgetGuard(budget_cfg, root / "logs" / "llm_usage.jsonl")
    return LLMRouter(routing_cfg, guard)
