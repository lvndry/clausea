import json

from src.analyser import _analysis_validator


def test_analysis_validator_passes_valid_response() -> None:
    content = json.dumps(
        {
            "summary": "This policy collects email addresses.",
            "scores": {
                "transparency": {"score": 7, "justification": "clear"},
                "data_collection_scope": {"score": 4, "justification": "broad"},
            },
            "verdict": "moderate",
            "keypoints": [],
            "critical_clauses": [],
        }
    )
    assert _analysis_validator(content) is True


def test_analysis_validator_fails_on_invalid_json() -> None:
    assert _analysis_validator("not json") is False


def test_analysis_validator_fails_missing_summary() -> None:
    content = json.dumps(
        {
            "scores": {"transparency": {"score": 7, "justification": "ok"}},
            "verdict": "moderate",
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_empty_summary() -> None:
    content = json.dumps(
        {
            "summary": "",
            "scores": {"transparency": {"score": 7, "justification": "ok"}},
            "verdict": "moderate",
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_missing_scores() -> None:
    content = json.dumps(
        {
            "summary": "This policy does things.",
            "verdict": "moderate",
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_empty_scores() -> None:
    content = json.dumps(
        {
            "summary": "This policy does things.",
            "scores": {},
            "verdict": "moderate",
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_when_scores_have_bare_integer_values() -> None:
    content = json.dumps(
        {
            "summary": "This policy collects data.",
            "scores": {"transparency": 7},
            "verdict": "moderate",
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_whitespace_only_summary() -> None:
    content = json.dumps(
        {
            "summary": "   ",
            "scores": {"transparency": {"score": 7, "justification": "ok"}},
            "verdict": "moderate",
        }
    )
    assert _analysis_validator(content) is False
