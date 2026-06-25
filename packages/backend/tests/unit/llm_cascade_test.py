"""The single free-first model cascade shared by every pipeline stage."""

from src.analyser import _ANALYSIS_PRIMARY, _OVERVIEW_PRIORITY
from src.llm import MODEL_PRIORITY
from src.services.extraction_service import _EXTRACTION_PRIMARY


def test_every_stage_uses_the_one_shared_cascade():
    for stage in (_ANALYSIS_PRIMARY, _EXTRACTION_PRIMARY, _OVERVIEW_PRIORITY):
        assert stage is MODEL_PRIORITY


def test_all_models_route_via_openrouter():
    for model in MODEL_PRIORITY:
        assert model.startswith("openrouter/"), f"{model} should route via OpenRouter"


def test_no_gpt5_or_native_paid_on_hot_path():
    assert not [model for model in MODEL_PRIORITY if model.startswith("gpt-5")]


def test_no_short_context_models_on_hot_path():
    for model in MODEL_PRIORITY:
        assert "gpt-oss" not in model, (
            f"{model} has 131K context — too short for whole-doc extraction"
        )


def test_free_models_use_free_slugs():
    free_models = [model for model in MODEL_PRIORITY if ":free" in model]
    assert len(free_models) >= 1
