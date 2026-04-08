import json
from urllib.error import HTTPError

import pytest

from injection_lab.providers import OpenAIResponsesProvider, ProviderError, make_provider


def test_responses_provider_extracts_output_text(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"output_text": "safe response"}).encode()

    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode())
        assert body["store"] is False
        assert body["input"][0]["role"] == "system"
        assert timeout == 60.0
        return FakeResponse()

    monkeypatch.setattr("injection_lab.providers.urlopen", fake_urlopen)
    provider = OpenAIResponsesProvider(api_key="test-key", model="test-model")
    assert provider.complete("system", "user") == "safe response"


def test_provider_error_does_not_include_provider_response_body(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr("injection_lab.providers.urlopen", fake_urlopen)
    provider = OpenAIResponsesProvider(api_key="test-key", model="test-model")
    with pytest.raises(ProviderError) as caught:
        provider.complete("system", "user")
    assert str(caught.value) == "http_401"
    assert "test-key" not in str(caught.value)


def test_real_provider_requires_explicit_model_selection(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("INJECTION_LAB_MODEL", raising=False)
    with pytest.raises(ProviderError) as caught:
        make_provider("openai", None)
    assert str(caught.value) == "missing_model"

