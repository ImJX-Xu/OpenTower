from __future__ import annotations

import json

from opentower_cli import openai_compatible_client as client_mod
from opentower_cli.openai_compatible_client import OpenAICompatibleMessagesClient


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_openai_compatible_client_autodiscovers_model_and_caches_it(monkeypatch) -> None:
    observed = {"models_calls": 0, "chat_calls": 0, "models": []}

    def fake_urlopen(req, timeout=0):
        if req.full_url.endswith("/models"):
            observed["models_calls"] += 1
            return _FakeHTTPResponse(
                {
                    "data": [
                        {"id": "deepseek-v4-flash"},
                        {"id": "deepseek-v4-pro"},
                    ]
                }
            )
        observed["chat_calls"] += 1
        payload = json.loads(req.data.decode("utf-8"))
        observed["models"].append(payload["model"])
        return _FakeHTTPResponse(
            {
                "id": "msg-1",
                "model": payload["model"],
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            }
        )

    monkeypatch.delenv("OPENTOWER_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr(client_mod.request, "urlopen", fake_urlopen)

    client = OpenAICompatibleMessagesClient(api_url="https://example.invalid/v1", api_key="sk-test")
    first = client.create_message(system="sys", user_text="hello")
    second = client.create_message(system="sys", user_text="hello again")

    assert first.model == "deepseek-v4-flash"
    assert second.model == "deepseek-v4-flash"
    assert observed["models_calls"] == 1
    assert observed["chat_calls"] == 2
    assert observed["models"] == ["deepseek-v4-flash", "deepseek-v4-flash"]


def test_openai_compatible_provider_status_autoselects_available_model(monkeypatch) -> None:
    def fake_urlopen(req, timeout=0):
        assert req.full_url == "https://example.invalid/v1/models"
        return _FakeHTTPResponse({"data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4-pro"}]})

    monkeypatch.setattr(client_mod.request, "urlopen", fake_urlopen)

    status = client_mod.provider_status(api_url="https://example.invalid/v1", api_key="sk-test")

    assert status.configured_model == "deepseek-v4-flash"
    assert status.model_available is True
    assert status.available_models == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert status.execute_ready is True
    assert "auto-selected" in str(status.status_detail)


def test_openai_compatible_provider_status_marks_unknown_explicit_model_unavailable(monkeypatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeHTTPResponse({"data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4-pro"}]})

    monkeypatch.setattr(client_mod.request, "urlopen", fake_urlopen)

    status = client_mod.provider_status(
        api_url="https://example.invalid/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
    )

    assert status.configured_model == "gpt-4o-mini"
    assert status.model_available is False
    assert status.execute_ready is False
    assert "was not found" in str(status.status_detail)
