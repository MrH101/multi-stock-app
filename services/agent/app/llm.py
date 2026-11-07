"""Client for Caimex, an OpenAI-compatible model gateway (https://api.caimex.ai).

The agent never depends on the model to *detect* a problem: rules do that. The model writes the
briefings and answers questions, and every caller has a non-AI fallback for when it is unavailable.
"""
import json
import logging
import time
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("llm")

RETRYABLE = {429, 500, 502, 503}


class LLMUnavailable(Exception):
    pass


@dataclass
class Completion:
    message: dict
    model: str
    cost_usd: float = 0.0

    @property
    def text(self) -> str:
        return self.message.get("content") or ""

    @property
    def tool_calls(self) -> list[dict]:
        return self.message.get("tool_calls") or []


@dataclass
class LLMStats:
    requests: int = 0
    failures: int = 0
    cost_usd: float = 0.0
    last_error: str | None = None
    last_model: str | None = None
    by_model: dict[str, int] = field(default_factory=dict)


class CaimexClient:
    def __init__(self, api_key: str, base_url: str, model: str, fallback_models: list[str],
                 timeout: float = 45, transport: httpx.BaseTransport | None = None):
        self.model = model
        self.fallback_models = fallback_models
        self.enabled = bool(api_key)
        self.stats = LLMStats()
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=httpx.Timeout(timeout, connect=5.0), transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                     "User-Agent": "multistock-agent/1.0"})

    def chat(self, messages: list[dict], *, tools: list[dict] | None = None, json_mode: bool = False,
             max_tokens: int = 900, temperature: float = 0.2, session_id: str | None = None) -> Completion:
        if not self.enabled:
            raise LLMUnavailable("No CAIMEX_API_KEY configured")
        body: dict = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                      "temperature": temperature}
        if self.fallback_models:
            body["fallback_models"] = self.fallback_models
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if session_id:
            body["session_id"] = session_id  # sticky routing + prompt caching per organisation

        self.stats.requests += 1
        delay = 1.0
        last: str = ""
        for attempt in range(3):
            try:
                r = self._http.post("/chat/completions", json=body)
            except httpx.TransportError as exc:
                last = f"network error: {exc}"
            else:
                if r.status_code == 200:
                    data = r.json()
                    model = data.get("model") or self.model
                    cost = float(r.headers.get("x-caimex-cost-usd") or 0)
                    self.stats.cost_usd += cost
                    self.stats.last_model = model
                    self.stats.last_error = None
                    self.stats.by_model[model] = self.stats.by_model.get(model, 0) + 1
                    return Completion(data["choices"][0]["message"], model, cost)
                last = f"HTTP {r.status_code}: {_error_message(r)}"
                if r.status_code not in RETRYABLE:
                    break  # 400/401/402/403/422 will not get better by retrying
            if attempt < 2:
                time.sleep(delay)
                delay *= 2
        self.stats.failures += 1
        self.stats.last_error = last
        log.warning("caimex request failed: %s", last)
        raise LLMUnavailable(last)

    def chat_json(self, messages: list[dict], **kwargs) -> tuple[dict, Completion]:
        completion = self.chat(messages, json_mode=True, **kwargs)
        return parse_json(completion.text), completion


def parse_json(text: str) -> dict:
    """Models occasionally wrap JSON in prose or code fences; take the outermost object."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


def _error_message(r: httpx.Response) -> str:
    try:
        data = r.json()
    except ValueError:
        return r.text[:200]
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message", ""))[:200]
    return str(data.get("detail", data))[:200] if isinstance(data, dict) else str(data)[:200]
