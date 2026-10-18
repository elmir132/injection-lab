"""Model providers. The default mock is local and deterministic."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """Safe-to-display provider error without request/response contents."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Provider(Protocol):
    name: str
    model: str
    tests_prompt: bool        # False for the offline mock, which ignores the prompt

    def complete(self, system_prompt: str, user_input: str) -> str: ...


@dataclass
class MockProvider:
    """A fixture mock for testing the harness, not a security evaluation."""

    name: str = "mock"
    model: str = "offline-fixture"
    tests_prompt: bool = False

    def complete(self, system_prompt: str, user_input: str) -> str:
        del system_prompt
        if "ILAB_DOC_OVERRIDE_8F31" in user_input:
            return "The meeting is Thursday."
        if "ILAB_TOOL_OVERRIDE_27C4" in user_input:
            return "The calendar lookup returned Orchard."
        if "private evaluation canary" in user_input.lower():
            return "I can't provide private evaluation data or hidden instructions."
        raise ProviderError("unknown_fixture")


@dataclass
class OpenAIResponsesProvider:
    """Minimal OpenAI Responses API client using only Python's standard library."""

    api_key: str
    model: str
    name: str = "openai"
    endpoint: str = "https://api.openai.com/v1/responses"
    timeout_seconds: float = 60.0
    max_output_tokens: int = 1000     # reasoning models spend part of this on thinking before they answer
    tests_prompt: bool = True

    def complete(self, system_prompt: str, user_input: str) -> str:
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # Do not include the provider's body; it may echo user content.
            raise ProviderError(f"http_{exc.code}") from None
        except (URLError, TimeoutError):
            raise ProviderError("network_error") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderError("invalid_response") from None

        output_text = data.get("output_text")
        if isinstance(output_text, str):
            return output_text
        # Be tolerant of responses that omit the convenience output_text field.
        pieces: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    pieces.append(content["text"])
        if not pieces:
            if data.get("status") == "incomplete":
                raise ProviderError("incomplete_output")      # ran out of tokens before answering
            raise ProviderError("missing_text_output")
        return "\n".join(pieces)


@dataclass
class OpenAICompatibleProvider:
    """Chat Completions client for any OpenAI-compatible endpoint (a gateway or a local server), standard library only."""

    api_key: str
    model: str
    base_url: str
    name: str = "openai-compatible"
    timeout_seconds: float = 120.0
    max_output_tokens: int = 1000     # reasoning models spend part of this on thinking before they answer
    tests_prompt: bool = True
    max_attempts: int = 5             # tries per request on HTTP 429 / 5xx, with 2, 4, 8, 16 s waits

    def complete(self, system_prompt: str, user_input: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            "max_tokens": self.max_output_tokens,
        }
        request = Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        data = None
        for attempt in range(self.max_attempts):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt + 1 < self.max_attempts:
                    time.sleep(2 ** (attempt + 1))                  # rate limits and brief outages: wait, then ask again
                    continue
                raise ProviderError(f"http_{exc.code}") from None   # never include the body; it may echo user content
            except (URLError, TimeoutError):
                raise ProviderError("network_error") from None
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ProviderError("invalid_response") from None
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content")
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError("invalid_response") from None
        if not isinstance(text, str) or not text.strip():
            if choice.get("finish_reason") == "length":
                raise ProviderError("incomplete_output")
            raise ProviderError("missing_text_output")
        return text


def make_provider(provider_name: str, model: str | None, max_output_tokens: int = 1000,
                  base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY") -> Provider:
    if provider_name == "mock":
        return MockProvider()
    if provider_name == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ProviderError("missing_openai_api_key")
        selected_model = model or os.environ.get("INJECTION_LAB_MODEL", "").strip()
        if not selected_model:
            raise ProviderError("missing_model")
        return OpenAIResponsesProvider(api_key=api_key, model=selected_model, max_output_tokens=max_output_tokens)
    if provider_name == "openai-compatible":
        if not base_url:
            raise ProviderError("missing_base_url")
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise ProviderError("missing_api_key")
        selected_model = model or os.environ.get("INJECTION_LAB_MODEL", "").strip()
        if not selected_model:
            raise ProviderError("missing_model")
        return OpenAICompatibleProvider(api_key=api_key, model=selected_model, base_url=base_url, max_output_tokens=max_output_tokens)
    raise ProviderError("unknown_provider")

