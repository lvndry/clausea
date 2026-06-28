"""Tests for generate_grade_reason."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import ModelResponse

from src.analyser import generate_grade_reason
from src.models.document import ConsumerCase, ConsumerExplainer, ConsumerSilentTopic


def _llm_response(content: str) -> ModelResponse:
    response = MagicMock(spec=ModelResponse)
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


def _explainer(**kwargs: object) -> ConsumerExplainer:
    base = {
        "headline": "Summary",
        "watch_out_for": [
            ConsumerCase(
                title="Data sharing",
                means_for_you="Your data may be shared with partners.",
                severity="high",
            )
        ],
        "good_to_know": ["You can delete your account."],
        "silent_on": [
            ConsumerSilentTopic(topic="data retention", why_it_matters="Unclear retention.")
        ],
    }
    base.update(kwargs)
    return ConsumerExplainer.model_validate(base)


@pytest.mark.asyncio
async def test_generate_grade_reason_returns_llm_text() -> None:
    explainer = _explainer()
    with patch(
        "src.analyser.acompletion_with_fallback",
        AsyncMock(return_value=_llm_response("Grade B reflects moderate data-sharing risk.")),
    ):
        reason = await generate_grade_reason("B", explainer)
    assert reason == "Grade B reflects moderate data-sharing risk."


@pytest.mark.asyncio
async def test_generate_grade_reason_truncates_long_llm_text() -> None:
    explainer = _explainer()
    long_text = "x" * 600
    with patch(
        "src.analyser.acompletion_with_fallback",
        AsyncMock(return_value=_llm_response(long_text)),
    ):
        reason = await generate_grade_reason("C", explainer)
    assert len(reason) == 500


@pytest.mark.asyncio
async def test_generate_grade_reason_falls_back_when_llm_fails() -> None:
    explainer = _explainer()
    with patch(
        "src.analyser.acompletion_with_fallback",
        AsyncMock(side_effect=RuntimeError("LLM down")),
    ):
        reason = await generate_grade_reason("B", explainer)
    assert "user-friendly" in reason.lower()


@pytest.mark.asyncio
async def test_generate_grade_reason_handles_empty_explainer_lists() -> None:
    explainer = ConsumerExplainer.model_validate(
        {
            "headline": "Sparse",
            "watch_out_for": [],
            "good_to_know": [],
            "silent_on": [],
        }
    )
    with patch(
        "src.analyser.acompletion_with_fallback",
        AsyncMock(return_value=_llm_response("Fallback explanation.")),
    ):
        reason = await generate_grade_reason("A", explainer)
    assert reason == "Fallback explanation."
