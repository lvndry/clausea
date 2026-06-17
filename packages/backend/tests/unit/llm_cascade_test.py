"""The single free-first model cascade shared by every pipeline stage."""

from src.analyser import _ANALYSIS_PRIMARY, _OVERVIEW_PRIORITY
from src.llm import _OPENROUTER_ALIASES, MODEL_PRIORITY
from src.services.extraction_service import _EXTRACTION_PRIMARY


def test_every_stage_uses_the_one_shared_cascade():
    for stage in (_ANALYSIS_PRIMARY, _EXTRACTION_PRIMARY, _OVERVIEW_PRIORITY):
        assert stage is MODEL_PRIORITY


def test_all_models_route_via_openrouter():
    for model in MODEL_PRIORITY:
        assert model.startswith("openrouter/"), f"{model} should route via OpenRouter"


def test_no_gpt5_or_native_paid_on_hot_path():
    assert not [model for model in MODEL_PRIORITY if model.startswith("gpt-5")]


def test_free_aliases_resolve_to_free_slugs():
    for alias in ("openrouter/gpt-oss-120b-free", "openrouter/gemma-free"):
        assert ":free" in _OPENROUTER_ALIASES[alias]
    assert "openrouter/owl-alpha" in _OPENROUTER_ALIASES
