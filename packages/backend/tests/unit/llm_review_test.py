from src.analyzers.llm_review import _coerce_review_pass


def test_coerce_review_pass_honors_declared_true() -> None:
    assert _coerce_review_pass(declared_pass=True, description="anything") is True


def test_coerce_review_pass_keeps_real_failure() -> None:
    assert (
        _coerce_review_pass(
            declared_pass=False,
            description="Headline overclaims indefinite retention without evidence.",
        )
        is False
    )


def test_coerce_review_pass_fixes_false_negative_no_unsupported() -> None:
    desc = "The headline claim is supported by privacy_signals. No unsupported strong claim found."
    assert _coerce_review_pass(declared_pass=False, description=desc) is True
