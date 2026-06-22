import json

from src.analyser import _analysis_validator


def test_analysis_validator_passes_valid_response() -> None:
    content = json.dumps(
        {
            "summary": "This policy collects email addresses.",
            "grade": "C",
            "grade_justification": "Broad collection with some transparency.",
            "scores": {
                "transparency": {"grade": "B", "justification": "clear"},
                "data_collection_scope": {"grade": "D", "justification": "broad"},
            },
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
            "grade": "C",
            "scores": {"transparency": {"grade": "B", "justification": "ok"}},
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_empty_summary() -> None:
    content = json.dumps(
        {
            "summary": "",
            "grade": "C",
            "scores": {"transparency": {"grade": "B", "justification": "ok"}},
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_missing_grade() -> None:
    content = json.dumps(
        {
            "summary": "This policy does things.",
            "scores": {"transparency": {"grade": "B", "justification": "ok"}},
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_empty_scores() -> None:
    content = json.dumps(
        {
            "summary": "This policy does things.",
            "grade": "C",
            "scores": {},
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_when_scores_have_bare_integer_values() -> None:
    content = json.dumps(
        {
            "summary": "This policy collects data.",
            "grade": "C",
            "scores": {"transparency": 7},
        }
    )
    assert _analysis_validator(content) is False


def test_analysis_validator_fails_whitespace_only_summary() -> None:
    content = json.dumps(
        {
            "summary": "   ",
            "grade": "C",
            "scores": {"transparency": {"grade": "B", "justification": "ok"}},
        }
    )
    assert _analysis_validator(content) is False
