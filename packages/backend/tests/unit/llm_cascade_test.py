"""The FREE-FIRST model cascade: native free Gemini -> OpenRouter free Kimi -> cheap paid.

A 429/failure auto-falls-through (acompletion_with_fallback), so ordering is the contract.
Paid tiers route via OpenRouter; only the free Gemini slot uses the native Google key.
"""

from src.analyser import _ANALYSIS_ESCALATION, _ANALYSIS_PRIMARY, _OVERVIEW_PRIORITY
from src.llm import _NO_TEMPERATURE_MODELS, _OPENROUTER_ALIASES, _sanitize_model_kwargs
from src.services.extraction_service import _EXTRACTION_PRIMARY

_FREE_FIRST = ["gemini-2.5-flash", "openrouter/kimi-k2.6-free"]


def test_analysis_extraction_overview_lead_free_first():
    assert _ANALYSIS_PRIMARY[:2] == _FREE_FIRST
    assert _EXTRACTION_PRIMARY[:2] == _FREE_FIRST
    assert _OVERVIEW_PRIORITY[:2] == _FREE_FIRST


def test_paid_tail_is_openrouter_and_no_native_paid_keys():
    # Slot 1 is the only native (free Gemini); every other model on the hot path is OpenRouter.
    for lst in (_ANALYSIS_PRIMARY, _EXTRACTION_PRIMARY, _OVERVIEW_PRIORITY):
        for model in lst[1:]:
            assert model.startswith("openrouter/"), f"{model} should route via OpenRouter"
    # No native gpt-5-mini / gpt-5-nano left on the analysis hot path.
    flat = set(_ANALYSIS_PRIMARY) | set(_EXTRACTION_PRIMARY) | set(_OVERVIEW_PRIORITY)
    assert not {m for m in flat if m.startswith("gpt-5")}


def test_escalation_is_cheap_paid_openrouter():
    assert _ANALYSIS_ESCALATION
    assert all(m.startswith("openrouter/") for m in _ANALYSIS_ESCALATION)


def test_free_openrouter_aliases_resolve_to_free_slugs():
    for alias in ("openrouter/kimi-k2.6-free", "openrouter/gemma-free"):
        resolved = _OPENROUTER_ALIASES[alias]
        assert resolved.startswith("openrouter/")
        assert ":free" in resolved


def test_free_tier_includes_both_openrouter_free_models():
    # Free tier (everything before the cheap-paid resilience tail) carries both
    # OpenRouter free models after the native free Gemini lead.
    for lst in (_ANALYSIS_PRIMARY, _EXTRACTION_PRIMARY, _OVERVIEW_PRIORITY):
        assert "openrouter/kimi-k2.6-free" in lst
        assert "openrouter/gemma-free" in lst


def test_temperature_kept_for_cascade_members_stripped_for_gpt5():
    # Free/paid cascade members accept temperature=0.
    for model in ("gemini-2.5-flash", "openrouter/kimi-k2.6-free", "openrouter/gpt-oss-120b-nitro"):
        assert model not in _NO_TEMPERATURE_MODELS
        assert _sanitize_model_kwargs(model, {"temperature": 0}).get("temperature") == 0
    # gpt-5 family still rejects a non-default temperature.
    assert "gpt-5-mini" in _NO_TEMPERATURE_MODELS
    assert "temperature" not in _sanitize_model_kwargs("gpt-5-mini", {"temperature": 0})


def test_no_phantom_gemini3_in_no_temperature_set():
    assert "gemini-3-flash-preview" not in _NO_TEMPERATURE_MODELS
