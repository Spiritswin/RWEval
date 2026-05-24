"""OpenAI-compatible LLM client."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from rw_eval.env import env_bool, env_int
from rw_eval.utils import first_json_object


class LLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        json_mode: Optional[bool] = None,
    ):
        self.base_url = (base_url if base_url is not None else os.environ.get("LLM_API_BASE_URL", "")).strip()
        self.api_key = api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")
        self.model = model if model is not None else os.environ.get("LLM_MODEL", "")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else env_int("LLM_TIMEOUT_SECONDS", 60)
        self.json_mode = json_mode if json_mode is not None else env_bool("LLM_JSON_MODE", False)
        self.request_retries = max(0, env_int("LLM_REQUEST_RETRIES", 3))
        self.json_retries = max(0, env_int("LLM_JSON_RETRIES", 2))
        self.retry_backoff_seconds = _env_float("LLM_RETRY_BACKOFF_SECONDS", 1.5)

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise LLMNotConfigured("LLM_API_BASE_URL, LLM_API_KEY, or LLM_MODEL is missing")

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_error: Optional[Exception] = None
        retry_count = self.json_retries if max_retries is None else max(0, max_retries)
        for attempt in range(retry_count + 1):
            if attempt:
                messages.append(
                    {
                        "role": "user",
                        "content": "Your previous response was not valid JSON. Return only a single valid JSON object.",
                    }
                )
            try:
                content = self.chat(messages, temperature=temperature)
                try:
                    return first_json_object(content)
                except ValueError as exc:
                    last_error = exc
                    repaired = self._repair_json(content)
                    if repaired is not None:
                        return repaired
                    continue
            except (ValueError, LLMError) as exc:
                last_error = exc
        raise LLMError(f"LLM JSON call failed: {last_error}")

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        endpoint = self._chat_endpoint()
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        request_body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(self.request_retries + 1):
            request = urllib.request.Request(
                endpoint,
                data=request_body,
                method="POST",
                headers=headers,
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                    data = json.loads(raw)
                    break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if (exc.code == 429 or 500 <= exc.code < 600) and attempt < self.request_retries:
                    last_error = LLMError(f"LLM HTTP {exc.code}: {detail}")
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
                if attempt < self.request_retries:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
                    continue
                raise LLMError(f"LLM request failed: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise LLMError(f"LLM returned invalid JSON envelope: {exc}") from exc
        else:
            raise LLMError(f"LLM request failed: {last_error}")

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response envelope: {data}") from exc

    def _chat_endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def _repair_json(self, invalid_content: str) -> Optional[Dict[str, Any]]:
        repair_messages = [
            {
                "role": "system",
                "content": "You repair malformed JSON. Return only one valid JSON object. Do not add commentary.",
            },
            {
                "role": "user",
                "content": (
                    "Repair this malformed JSON-like response into valid JSON without changing its meaning. "
                    "Return only valid JSON:\n\n"
                    f"{invalid_content}"
                ),
            },
        ]
        try:
            repaired_content = self.chat(repair_messages, temperature=0.0)
            return first_json_object(repaired_content)
        except (LLMError, ValueError):
            return None


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    pass


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
