"""Validator-driven fallback: a model whose output fails validation is skipped for the
next (stronger) model in the same priority list. Replaces the old separate escalation pass.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from litellm import ModelResponse

from src.llm import (
    AllModelsFailedError,
    Model,
    _completion_with_fallback_impl,
    _extract_json_from_response,
)

_DUMMY_MODEL = Model(model="dummy", api_key="k")


def _make_response(content: str, model: str = "m1") -> ModelResponse:
    response = MagicMock(spec=ModelResponse)
    response.model = model
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


def test_extract_json_from_response_returns_content() -> None:
    response = _make_response('{"key": "value"}')
    assert _extract_json_from_response(response) == '{"key": "value"}'


def test_extract_json_from_response_raises_on_empty_content() -> None:
    response = _make_response("")
    with pytest.raises(ValueError, match="empty"):
        _extract_json_from_response(response)


def test_extract_json_from_response_raises_on_none_content() -> None:
    resp = MagicMock(spec=ModelResponse)
    choice = MagicMock()
    choice.message.content = None
    resp.choices = [choice]
    with pytest.raises(ValueError):
        _extract_json_from_response(resp)


def test_extract_json_from_response_raises_on_none_message() -> None:
    resp = MagicMock(spec=ModelResponse)
    choice = MagicMock()
    choice.message = None
    resp.choices = [choice]
    with pytest.raises(ValueError, match="None"):
        _extract_json_from_response(resp)


def _sequential_completion_fn(responses: list[ModelResponse]):
    calls = {"count": 0}

    async def completion_fn(**_kwargs) -> ModelResponse:
        response = responses[calls["count"]]
        calls["count"] += 1
        return response

    return completion_fn, calls


@pytest.mark.asyncio
async def test_returns_first_model_when_no_validator() -> None:
    first = _make_response('{"a": 1}', "m1")
    completion_fn, calls = _sequential_completion_fn([first, _make_response("{}", "m2")])
    with patch("src.llm.get_model", return_value=_DUMMY_MODEL), patch("src.llm.track_usage"):
        result = await _completion_with_fallback_impl(
            messages=[], completion_fn=completion_fn, model_priority=["m1", "m2"]
        )
    assert result is first
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_validation_failure_advances_to_next_model() -> None:
    weak = _make_response("{}", "m1")
    strong = _make_response('{"data": [1]}', "m2")
    completion_fn, calls = _sequential_completion_fn([weak, strong])

    def validator(content: str) -> bool:
        return json.loads(content).get("data") is not None

    with patch("src.llm.get_model", return_value=_DUMMY_MODEL), patch("src.llm.track_usage"):
        result = await _completion_with_fallback_impl(
            messages=[],
            completion_fn=completion_fn,
            model_priority=["m1", "m2"],
            validator=validator,
        )
    assert result is strong
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_returns_last_response_when_all_fail_validation() -> None:
    first = _make_response("{}", "m1")
    last = _make_response("{}", "m2")
    completion_fn, calls = _sequential_completion_fn([first, last])
    with patch("src.llm.get_model", return_value=_DUMMY_MODEL), patch("src.llm.track_usage"):
        result = await _completion_with_fallback_impl(
            messages=[],
            completion_fn=completion_fn,
            model_priority=["m1", "m2"],
            validator=lambda _content: False,
        )
    assert result is last  # partial data beats blocking the pipeline
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_raises_when_every_model_errors() -> None:
    async def completion_fn(**_kwargs) -> ModelResponse:
        raise RuntimeError("boom")

    with patch("src.llm.get_model", return_value=_DUMMY_MODEL), patch("src.llm.track_usage"):
        with pytest.raises(AllModelsFailedError):
            await _completion_with_fallback_impl(
                messages=[], completion_fn=completion_fn, model_priority=["m1", "m2"]
            )
