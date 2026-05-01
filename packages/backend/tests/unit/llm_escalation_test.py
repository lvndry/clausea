import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import ModelResponse

from src.llm import _extract_json_from_response, acompletion_with_escalation


def _make_response(content: str, model: str = "gpt-5-mini") -> ModelResponse:
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


@pytest.mark.asyncio
async def test_escalation_escalates_when_primary_returns_empty_content() -> None:
    primary_response = _make_response("", model="gpt-5-mini")
    escalation_response = _make_response('{"data": [1]}', model="gpt-5.4-mini")

    call_count = 0

    async def mock_fallback(messages, model_priority, **kwargs):
        nonlocal call_count
        call_count += 1
        return primary_response if call_count == 1 else escalation_response

    with patch("src.llm.acompletion_with_fallback", side_effect=mock_fallback):
        result = await acompletion_with_escalation(
            messages=[{"role": "user", "content": "test"}],
            primary=["gpt-5-mini"],
            escalation=["gpt-5.4-mini"],
            validator=lambda c: True,
        )

    assert result is escalation_response
    assert call_count == 2


@pytest.mark.asyncio
async def test_escalation_returns_primary_when_valid() -> None:
    primary_response = _make_response('{"ok": true}', model="gpt-5-mini")

    with patch("src.llm.acompletion_with_fallback", new_callable=AsyncMock) as mock_fb:
        mock_fb.return_value = primary_response
        result = await acompletion_with_escalation(
            messages=[{"role": "user", "content": "test"}],
            primary=["gpt-5-mini"],
            escalation=["gpt-5.4-mini"],
            validator=lambda c: True,
        )

    assert result is primary_response
    assert mock_fb.call_count == 1


@pytest.mark.asyncio
async def test_escalation_calls_escalation_model_when_primary_invalid() -> None:
    primary_response = _make_response("{}", model="gpt-5-mini")
    escalation_response = _make_response('{"data": [1]}', model="gpt-5.4-mini")

    call_count = 0

    async def mock_fallback(messages, model_priority, **kwargs):
        nonlocal call_count
        call_count += 1
        return primary_response if call_count == 1 else escalation_response

    with patch("src.llm.acompletion_with_fallback", side_effect=mock_fallback):
        result = await acompletion_with_escalation(
            messages=[{"role": "user", "content": "test"}],
            primary=["gpt-5-mini"],
            escalation=["gpt-5.4-mini"],
            validator=lambda c: json.loads(c).get("data") is not None,
        )

    assert result is escalation_response
    assert call_count == 2


@pytest.mark.asyncio
async def test_escalation_returns_escalated_response_even_when_both_fail_validation() -> None:
    primary_response = _make_response("{}", model="gpt-5-mini")
    escalation_response = _make_response("{}", model="gpt-5.4-mini")

    call_count = 0

    async def mock_fallback(messages, model_priority, **kwargs):
        nonlocal call_count
        call_count += 1
        return primary_response if call_count == 1 else escalation_response

    with patch("src.llm.acompletion_with_fallback", side_effect=mock_fallback):
        result = await acompletion_with_escalation(
            messages=[{"role": "user", "content": "test"}],
            primary=["gpt-5-mini"],
            escalation=["gpt-5.4-mini"],
            validator=lambda c: False,
        )

    assert result is escalation_response
    assert call_count == 2
