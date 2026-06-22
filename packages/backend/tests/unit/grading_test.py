"""Tests for A–E letter grade utilities."""

from src.utils.grading import (
    aggregate_dimension_grades,
    coerce_grade,
    grade_to_risk_score,
    score_to_grade,
)


def test_coerce_grade_normalizes_input() -> None:
    assert coerce_grade("b") == "B"
    assert coerce_grade("invalid", default="C") == "C"


def test_score_to_grade_legacy_mapping() -> None:
    assert score_to_grade(9) == "A"
    assert score_to_grade(5) == "C"
    assert score_to_grade(1) == "E"


def test_grade_to_risk_score() -> None:
    assert grade_to_risk_score("A") == 1
    assert grade_to_risk_score("C") == 5
    assert grade_to_risk_score("E") == 9


def test_aggregate_dimension_grades_weighted() -> None:
    overall = aggregate_dimension_grades(
        {
            "transparency": "A",
            "data_collection_scope": "C",
            "user_control": "B",
            "third_party_sharing": "D",
        }
    )
    assert overall in {"B", "C"}
