"""Gemma native transport: request shape (focused regression tests).

Gemma 4 spends output budget on hidden thoughts first; at tight budgets it
returned zero candidate tokens. The provider floors maxOutputTokens at
4096 and must not send thinkingConfig (the native API rejects it with
INVALID_ARGUMENT). These tests capture the exact request offline.
"""
import io
import json
import urllib.request

from second_source.model_gateway import GemmaTestProvider, ModelRequest


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        doc = {
            "candidates": [
                {
                    "content": {"parts": [{"text": '{"hypotheses": []}'}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
                "thoughtsTokenCount": 3,
            },
        }
        return _Resp(json.dumps(doc).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


def test_gemma_request_floors_output_budget_without_thinking_config(monkeypatch):
    captured = _capture(monkeypatch)
    provider = GemmaTestProvider("test-key-not-real")
    response = provider.complete(
        ModelRequest(
            stage="hypothesize",
            prompt_version="hypothesize-v1",
            messages=(
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "obs"},
            ),
            json_schema={"type": "object", "properties": {"hypotheses": {"type": "array"}}},
            max_output_tokens=512,
        )
    )
    config = captured["payload"]["generationConfig"]
    assert config["maxOutputTokens"] == 8000
    assert config["responseSchema"]["type"] == "OBJECT"
    assert config["responseSchema"]["properties"]["hypotheses"]["type"] == "ARRAY"
    assert "thinkingConfig" not in config
    assert config["responseMimeType"] == "application/json"
    assert captured["payload"]["systemInstruction"]["parts"][0]["text"].endswith("sys")
    assert "ONLY one JSON object" in captured["payload"]["systemInstruction"]["parts"][0]["text"]
    assert "generativelanguage.googleapis.com" in captured["url"]
    assert "gemma-4-26b-a4b-it:generateContent" in captured["url"]
    assert response.parsed == {"hypotheses": []}
    assert response.provider == "gemma-test"
    assert response.input_tokens == 10
    assert response.output_tokens == 5


def test_gemma_request_keeps_larger_budget(monkeypatch):
    captured = _capture(monkeypatch)
    provider = GemmaTestProvider("test-key-not-real")
    provider.complete(
        ModelRequest(
            stage="hypothesize",
            prompt_version="hypothesize-v1",
            messages=({"role": "user", "content": "obs"},),
            max_output_tokens=6000,
        )
    )
    assert captured["payload"]["generationConfig"]["maxOutputTokens"] == 8000
