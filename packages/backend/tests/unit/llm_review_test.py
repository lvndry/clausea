from src.analyzers.llm_review import _parse_check_passed


def test_parse_check_passed_when_failure_is_null() -> None:
    assert _parse_check_passed({"check": "UNSUPPORTED_CLAIMS", "failure": None}) is True


def test_parse_check_passed_when_failure_is_empty_string() -> None:
    assert _parse_check_passed({"check": "UNSUPPORTED_CLAIMS", "failure": "   "}) is True


def test_parse_check_passed_when_failure_is_present() -> None:
    assert (
        _parse_check_passed(
            {
                "check": "UNSUPPORTED_CLAIMS",
                "failure": "Headline overclaims indefinite retention without evidence.",
            }
        )
        is False
    )


def test_parse_check_passed_legacy_pass_boolean() -> None:
    assert _parse_check_passed({"check": "UNSUPPORTED_CLAIMS", "pass": True}) is True
    assert _parse_check_passed({"check": "UNSUPPORTED_CLAIMS", "pass": False}) is False
