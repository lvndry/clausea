"""The single free-first model cascade shared by every pipeline stage.

Slot 1 is the native free Gemini; every other model routes via OpenRouter. A 429/failure
auto-falls-through (acompletion_with_fallback), so ordering is the contract. ESCALATION is
the paid tail of the same list.
"""

from src.analyser import _ANALYSIS_PRIMARY, _OVERVIEW_PRIORITY
from src.document_processor import _CLASSIFICATION_PRIORITY
from src.llm import _OPENROUTER_ALIASES, MODEL_PRIORITY
from src.services.extraction_service import _EXTRACTION_PRIMARY


def test_every_stage_uses_the_one_shared_cascade():
    for stage in (
        _ANALYSIS_PRIMARY,
        _EXTRACTION_PRIMARY,
        _OVERVIEW_PRIORITY,
        _CLASSIFICATION_PRIORITY,
    ):
        assert stage is MODEL_PRIORITY


def test_slot1_is_native_gemini_rest_openrouter():
    assert MODEL_PRIORITY[0] == "gemini-2.5-flash-lite"
    assert not MODEL_PRIORITY[0].startswith("openrouter/")
    for model in MODEL_PRIORITY[1:]:
        assert model.startswith("openrouter/"), f"{model} should route via OpenRouter"


def test_no_gpt5_or_native_paid_on_hot_path():
    assert not [model for model in MODEL_PRIORITY if model.startswith("gpt-5")]


def test_free_aliases_resolve_to_free_slugs():
    for alias in ("openrouter/gpt-oss-120b-free", "openrouter/gemma-free"):
        assert ":free" in _OPENROUTER_ALIASES[alias]
    assert "openrouter/owl-alpha" in _OPENROUTER_ALIASES
