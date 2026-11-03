"""Offline check of the Gemini wire path: every response schema FINN uses goes through the real
google-genai request builder (only the HTTP call is faked), and the wrapper parses the reply.
This catches schema features the SDK rejects, without a key or network. It is NOT a live test."""
import json, typing, types as pytypes
import pytest
from pydantic import BaseModel

import finn.llm as llm
from google.genai import _api_client

from finn.push.classify import _Batch
from finn.push.refresh import _OneLine
from finn.push.results import FilingNumbers
from finn.push.mgmt import MgmtChange
from finn.pull.promises import GuidanceList, Check
from finn.pull.agent import Business, BullBear, Answer

SCHEMAS = [_Batch, _OneLine, FilingNumbers, MgmtChange, GuidanceList, Check, Business, BullBear, Answer]


def sample(tp):
    origin = typing.get_origin(tp)
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return {n: sample(f.annotation) for n, f in tp.model_fields.items()}
    if origin is typing.Literal:
        return typing.get_args(tp)[0]
    if origin in (typing.Union, pytypes.UnionType):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        return sample(args[0])
    if origin is list:
        return [sample(typing.get_args(tp)[0])]
    return {str: "x", int: 1, float: 1.5, bool: True}.get(tp, "x")


@pytest.fixture()
def wire(monkeypatch):
    sent, replies = [], []
    def fake_request(self, http_request, http_options=None, stream=False):
        sent.append(json.loads(http_request.data) if isinstance(http_request.data, (str, bytes)) else http_request.data)
        return _api_client.HttpResponse(headers={}, response_stream=[json.dumps(replies.pop(0))])
    monkeypatch.setattr(_api_client.BaseApiClient, "_request", fake_request)
    monkeypatch.setattr(llm, "GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(llm, "_client", None)
    from finn.db import init_db
    init_db()
    return sent, replies


def reply(obj, finish="STOP"):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": obj if isinstance(obj, str) else json.dumps(obj)}]},
                            "finishReason": finish}], "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 7}}


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda s: s.__name__)
def test_schema_serialises_and_parses(wire, schema):
    sent, replies = wire
    replies.append(reply(sample(schema)))
    out = llm.generate(schema, tier="fast", purpose=f"wire_{schema.__name__}", prompt="p")
    assert isinstance(out, schema)
    cfg = sent[-1]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert "responseSchema" in cfg or "responseJsonSchema" in cfg
    assert "test-key-not-real" not in json.dumps(sent[-1])          # key never in the body


def test_truncated_output_retries_with_more_tokens(wire):
    sent, replies = wire
    replies += [reply('{"summary": "Board appro', finish="MAX_TOKENS"), reply({"summary": "Board approved a dividend."})]
    out = llm.generate(_OneLine, tier="fast", purpose="wire_truncation", prompt="p2", max_output_tokens=200)
    assert out.summary.startswith("Board approved")
    assert sent[1]["generationConfig"]["maxOutputTokens"] > sent[0]["generationConfig"]["maxOutputTokens"]


def test_cache_hit_makes_no_second_call(wire):
    sent, replies = wire
    replies.append(reply({"summary": "Cached."}))
    llm.generate(_OneLine, tier="fast", purpose="wire_cache", prompt="same")
    llm.generate(_OneLine, tier="fast", purpose="wire_cache", prompt="same")
    assert len(sent) == 1
