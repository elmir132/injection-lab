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



class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_compatible_provider_builds_chat_request_and_extracts_text(monkeypatch):
    from injection_lab.providers import OpenAICompatibleProvider

    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        body = json.loads(request.data.decode())
        assert body["messages"][0] == {"role": "system", "content": "system"}
        assert body["messages"][1]["role"] == "user"
        return _Resp({"choices": [{"message": {"content": "safe answer"}, "finish_reason": "stop"}]})

    monkeypatch.setattr("injection_lab.providers.urlopen", fake_urlopen)
    provider = OpenAICompatibleProvider(api_key="test-key", model="m", base_url="https://gateway.example/v1/")
    assert provider.complete("system", "user") == "safe answer"
    assert seen["url"] == "https://gateway.example/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"


def test_compatible_provider_reports_truncated_and_empty_output(monkeypatch):
    from injection_lab.providers import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(api_key="k", model="m", base_url="https://x/v1")
    monkeypatch.setattr("injection_lab.providers.urlopen", lambda r, timeout: _Resp({"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}))
    with pytest.raises(ProviderError) as caught:
        provider.complete("s", "u")
    assert str(caught.value) == "incomplete_output"
    monkeypatch.setattr("injection_lab.providers.urlopen", lambda r, timeout: _Resp({"choices": [{"message": {"content": None}, "finish_reason": "stop"}]}))
    with pytest.raises(ProviderError) as caught:
        provider.complete("s", "u")
    assert str(caught.value) == "missing_text_output"
    monkeypatch.setattr("injection_lab.providers.urlopen", lambda r, timeout: _Resp({"unexpected": 1}))
    with pytest.raises(ProviderError) as caught:
        provider.complete("s", "u")
    assert str(caught.value) == "invalid_response"


def test_compatible_provider_error_hides_body_and_setup_checks(monkeypatch):
    from injection_lab.providers import OpenAICompatibleProvider

    def boom(request, timeout):
        raise HTTPError(request.full_url, 429, "slow down", {}, None)

    monkeypatch.setattr("injection_lab.providers.urlopen", boom)
    monkeypatch.setattr("injection_lab.providers.time.sleep", lambda s: None)
    with pytest.raises(ProviderError) as caught:
        OpenAICompatibleProvider(api_key="k", model="m", base_url="https://x/v1").complete("s", "u")
    assert str(caught.value) == "http_429"
    monkeypatch.delenv("SOME_KEY", raising=False)
    with pytest.raises(ProviderError) as caught:
        make_provider("openai-compatible", "m", base_url="https://x/v1", api_key_env="SOME_KEY")
    assert str(caught.value) == "missing_api_key"
    with pytest.raises(ProviderError) as caught:
        make_provider("openai-compatible", "m")
    assert str(caught.value) == "missing_base_url"


def test_compatible_provider_retries_rate_limit_then_succeeds(monkeypatch):
    from injection_lab.providers import OpenAICompatibleProvider

    calls = {"n": 0}
    waits = []

    def flaky(request, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise HTTPError(request.full_url, 429, "slow down", {}, None)
        return _Resp({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    monkeypatch.setattr("injection_lab.providers.urlopen", flaky)
    monkeypatch.setattr("injection_lab.providers.time.sleep", waits.append)
    assert OpenAICompatibleProvider(api_key="k", model="m", base_url="https://x/v1").complete("s", "u") == "ok"
    assert calls["n"] == 3 and waits == [2, 4]


def test_compatible_provider_does_not_retry_client_errors(monkeypatch):
    from injection_lab.providers import OpenAICompatibleProvider

    calls = {"n": 0}

    def denied(request, timeout):
        calls["n"] += 1
        raise HTTPError(request.full_url, 401, "no", {}, None)

    monkeypatch.setattr("injection_lab.providers.urlopen", denied)
    with pytest.raises(ProviderError):
        OpenAICompatibleProvider(api_key="k", model="m", base_url="https://x/v1").complete("s", "u")
    assert calls["n"] == 1


def test_compatible_provider_refuses_plain_http_to_a_remote_host_but_allows_localhost(monkeypatch):
    monkeypatch.setenv("SOME_KEY", "k")
    with pytest.raises(ProviderError) as caught:
        make_provider("openai-compatible", "m", base_url="http://gateway.example/v1", api_key_env="SOME_KEY")
    assert str(caught.value) == "insecure_base_url"
    assert make_provider("openai-compatible", "m", base_url="http://localhost:11434/v1", api_key_env="SOME_KEY").model == "m"
