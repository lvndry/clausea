from src.analyzers.llm_review import LLMReviewCheck, LLMReviewResult
from src.analyzers.overview_guards import (
    OverviewValidationResult,
    check_actions_actionable,
    check_dangers_benefits_balance,
    check_e_grade_on_silence,
    check_rights_have_paths,
    find_long_sentences,
    format_overview_retry_feedback,
    merge_llm_review,
    validate_headline_length,
    validate_headline_not_empty,
    validate_overview,
    validate_summary_length,
)


def test_validate_summary_length_empty_is_valid() -> None:
    assert validate_summary_length("") is True


def test_validate_summary_length_at_limit_passes() -> None:
    assert (
        validate_summary_length(
            "one two three four five six seven eight nine ten "
            "eleven twelve thirteen fourteen fifteen sixteen "
            "seventeen eighteen nineteen twenty"
        )
        is True
    )


def test_validate_summary_length_over_limit_fails() -> None:
    assert (
        validate_summary_length(
            "one two three four five six seven eight nine ten "
            "eleven twelve thirteen fourteen fifteen sixteen "
            "seventeen eighteen nineteen twenty twentyone"
        )
        is False
    )


def test_validate_headline_length_none_is_valid() -> None:
    assert validate_headline_length(None) is True


def test_validate_headline_length_empty_is_valid() -> None:
    assert validate_headline_length("   ") is True


def test_validate_headline_length_at_limit_passes() -> None:
    words = "word " * 25
    assert validate_headline_length(words.strip()) is True


def test_validate_headline_length_over_limit_fails() -> None:
    words = "word " * 26
    assert validate_headline_length(words.strip()) is False


def test_validate_headline_not_empty_thin_evidence_allows_empty() -> None:
    assert validate_headline_not_empty(None, has_adequate_evidence=False) is True
    assert validate_headline_not_empty("   ", has_adequate_evidence=False) is True


def test_validate_headline_not_empty_adequate_evidence_rejects_empty() -> None:
    assert validate_headline_not_empty(None, has_adequate_evidence=True) is False
    assert validate_headline_not_empty("   ", has_adequate_evidence=True) is False


def test_validate_headline_not_empty_adequate_evidence_accepts_filled() -> None:
    assert validate_headline_not_empty("Coinbase sells data.", has_adequate_evidence=True) is True


def test_find_long_sentences_none_when_short() -> None:
    assert find_long_sentences("Short sentence. Another one!") == []


def test_find_long_sentences_returns_overword_counts() -> None:
    long_one = " ".join(["word"] * 40)
    text = f"Short. {long_one}. Also short."
    assert find_long_sentences(text) == [40]


def test_find_long_sentences_respects_custom_max() -> None:
    text = " ".join(["word"] * 10) + ". "
    assert find_long_sentences(text, max_words=5) == [10]


def test_check_e_grade_on_silence_not_e_grade() -> None:
    stances = [{"status": "missing", "evidence_count": 0}] * 10
    assert check_e_grade_on_silence("D", stances) is False


def test_check_e_grade_on_silence_with_evidence() -> None:
    stances = [{"status": "missing", "evidence_count": 1}] * 8
    stances.append({"status": "found", "evidence_count": 2})
    assert check_e_grade_on_silence("E", stances) is False


def test_check_e_grade_on_silence_majority_silent_no_evidence() -> None:
    stances = [{"status": "missing", "evidence_count": 0}] * 8
    stances.append({"status": "found", "evidence_count": 0})
    assert check_e_grade_on_silence("E", stances) is True


def test_check_e_grade_on_silence_not_enough_silence() -> None:
    stances = [{"status": "missing", "evidence_count": 0}] * 5
    stances += [{"status": "found", "evidence_count": 0}] * 5
    assert check_e_grade_on_silence("E", stances) is False


def test_check_dangers_benefits_balance_few_dangers_ok() -> None:
    assert check_dangers_benefits_balance(["a", "b"], [], "anything") is True


def test_check_dangers_benefits_balance_enough_benefits_ok() -> None:
    dangers = ["d"] * 5
    benefits = ["b1", "b2"]
    assert check_dangers_benefits_balance(dangers, benefits, "no ack") is True


def test_check_dangers_benefits_balance_imbalance_fails() -> None:
    dangers = ["d"] * 6
    benefits = ["only one"]
    assert check_dangers_benefits_balance(dangers, benefits, "anything") is False


def test_check_rights_have_paths_all_have_paths() -> None:
    rights = [
        "Delete at https://x.com/delete",
        "Email privacy@x.com",
        "Opt out in account settings",
    ]
    ok, ratio = check_rights_have_paths(rights)
    assert ok is True
    assert ratio == 1.0


def test_check_rights_have_paths_pathless_with_contact_ok() -> None:
    rights = ["Contact the company to request access", "Email the company for a copy"]
    ok, ratio = check_rights_have_paths(rights)
    assert ok is True
    assert ratio == 0.0


def test_check_rights_have_paths_mostly_pathless_fails() -> None:
    rights = ["Request access", "Correct your data", "Withdraw consent", "https://x.com/delete"]
    ok, ratio = check_rights_have_paths(rights)
    assert ok is False
    assert ratio < 0.7


def test_check_rights_have_paths_empty() -> None:
    ok, ratio = check_rights_have_paths([])
    assert ok is True
    assert ratio == 1.0


def test_check_actions_actionable_all_actionable() -> None:
    actions = [
        "Delete your account at https://x.com/delete",
        "Opt out in settings",
        "Contact privacy@x.com",
        "Unsubscribe via the email link",
    ]
    ok, ratio = check_actions_actionable(actions)
    assert ok is True
    assert ratio == 1.0


def test_check_actions_actionable_too_vague_fails() -> None:
    actions = [
        "Be careful with your data",
        "Read the policy carefully",
        "Consider your privacy",
        "Think about sharing",
        "Stay informed",
    ]
    ok, ratio = check_actions_actionable(actions)
    assert ok is False
    assert ratio < 0.7


def test_check_actions_actionable_empty() -> None:
    ok, ratio = check_actions_actionable([])
    assert ok is True
    assert ratio == 1.0


def test_validate_overview_clean_passes() -> None:
    overview = {
        "summary": "Coinbase offers strong self-service privacy controls.",
        "headline_claim": "Coinbase provides a self-service deletion path in account settings.",
        "grade": "C",
        "grade_justification": "The product collects moderate data but offers real controls.",
        "your_rights": [
            "Delete at https://x.com/delete",
            "Email privacy@x.com",
            "Opt out in account settings",
        ],
        "dangers": ["Shares identifiers for advertising", "Retains data for 90 days"],
        "benefits": ["Self-service deletion", "Encryption in transit"],
        "recommended_actions": [
            "Delete your account at https://x.com/delete",
            "Opt out in settings",
        ],
        "privacy_signals": {"sells_data": "no", "ai_training_on_user_data": "no"},
        "topic_stances": [
            {"status": "found", "evidence_count": 3, "supporting_citations": []},
            {"status": "found", "evidence_count": 2, "supporting_citations": []},
        ],
    }
    result = validate_overview(overview, has_adequate_evidence=True)
    assert isinstance(result, OverviewValidationResult)
    assert result.should_re_roll is False
    assert result.re_roll_reasons == []


def test_validate_overview_empty_headline_with_evidence_re_rolls() -> None:
    overview = {
        "summary": "Coinbase offers strong self-service privacy controls.",
        "headline_claim": None,
        "grade": "C",
        "grade_justification": "Moderate collection with real controls.",
        "privacy_signals": {},
        "topic_stances": [],
    }
    result = validate_overview(overview, has_adequate_evidence=True)
    assert result.should_re_roll is True
    assert result.checks_passed["headline_not_empty"] is False
    assert any("Headline is empty" in r for r in result.re_roll_reasons)


def test_validate_overview_empty_headline_thin_evidence_passes() -> None:
    overview = {
        "summary": "Coinbase offers strong self-service privacy controls.",
        "headline_claim": None,
        "grade": "C",
        "grade_justification": "Moderate collection with real controls.",
    }
    result = validate_overview(overview, has_adequate_evidence=False)
    assert result.should_re_roll is False


def test_validate_overview_e_on_silence_re_rolls() -> None:
    stances = [{"status": "missing", "evidence_count": 0}] * 8
    stances.append({"status": "found", "evidence_count": 0})
    overview = {
        "summary": "Service does not disclose much about its practices.",
        "headline_claim": "Service is silent on most privacy topics.",
        "grade": "E",
        "grade_justification": "Few disclosures are present.",
        "topic_stances": stances,
    }
    result = validate_overview(overview, has_adequate_evidence=True)
    assert result.should_re_roll is True
    assert result.checks_passed["no_e_grade_on_silence"] is False


def test_validate_overview_warnings_for_medium_issues() -> None:
    long_summary = " ".join(["word"] * 25)
    long_sentence = " ".join(["word"] * 40)
    overview = {
        "summary": long_summary,
        "headline_claim": "Service collects data from users.",
        "grade": "D",
        "grade_justification": long_sentence,
        "your_rights": ["Request access", "Correct data", "Withdraw consent"],
        "dangers": ["d"] * 6,
        "benefits": ["only one benefit"],
        "recommended_actions": [
            "Be careful",
            "Read carefully",
            "Stay informed",
            "Consider sharing",
            "Think about it",
        ],
        "privacy_signals": {},
        "topic_stances": [],
    }
    result = validate_overview(overview, has_adequate_evidence=True)
    assert result.should_re_roll is False
    assert result.checks_passed["summary_length"] is False
    assert result.checks_passed["dangers_benefits_balance"] is False
    assert result.checks_passed["rights_have_paths"] is False
    assert result.checks_passed["actions_actionable"] is False
    assert result.checks_passed["no_long_sentences"] is False
    assert any("Summary exceeds" in w for w in result.warnings)


def test_merge_llm_review_none_returns_deterministic_unchanged() -> None:
    det = OverviewValidationResult(
        should_re_roll=True,
        re_roll_reasons=["headline empty"],
        warnings=["summary too long"],
        checks_passed={"headline_not_empty": False, "summary_length": False},
    )
    merged = merge_llm_review(det, None)
    assert merged is det


def test_merge_llm_review_high_severity_adds_to_re_roll() -> None:
    det = OverviewValidationResult(
        should_re_roll=False,
        re_roll_reasons=[],
        warnings=[],
        checks_passed={},
    )
    llm = LLMReviewResult(
        checks=[
            LLMReviewCheck(
                check="UNSUPPORTED_CLAIMS",
                passed=False,
                severity="high",
                description="Claims sale but signal is no",
            ),
            LLMReviewCheck(check="LEGAL_JARGON", passed=True, severity="medium"),
        ]
    )
    merged = merge_llm_review(det, llm)
    assert merged.should_re_roll is True
    assert any("UNSUPPORTED_CLAIMS" in r for r in merged.re_roll_reasons)
    assert merged.checks_passed["llm_unsupported_claims"] is False
    assert merged.checks_passed["llm_legal_jargon"] is True


def test_merge_llm_review_medium_severity_adds_to_warnings() -> None:
    det = OverviewValidationResult(
        should_re_roll=False,
        re_roll_reasons=[],
        warnings=[],
        checks_passed={},
    )
    llm = LLMReviewResult(
        checks=[
            LLMReviewCheck(
                check="LEGAL_JARGON",
                passed=False,
                severity="medium",
                description="Uses 'notwithstanding'",
            ),
            LLMReviewCheck(
                check="GENERIC_HEADLINE",
                passed=False,
                severity="medium",
                description="Generic opener",
            ),
        ]
    )
    merged = merge_llm_review(det, llm)
    assert merged.should_re_roll is False
    assert len(merged.warnings) == 2
    assert all("[LLM]" in w for w in merged.warnings)


def test_merge_llm_review_all_pass_no_changes() -> None:
    det = OverviewValidationResult(
        should_re_roll=False,
        re_roll_reasons=[],
        warnings=["summary too long"],
        checks_passed={"summary_length": False},
    )
    llm = LLMReviewResult(
        checks=[
            LLMReviewCheck(check="UNSUPPORTED_CLAIMS", passed=True, severity="high"),
            LLMReviewCheck(check="LEGAL_JARGON", passed=True, severity="medium"),
        ]
    )
    merged = merge_llm_review(det, llm)
    assert merged.should_re_roll is False
    assert merged.re_roll_reasons == []
    assert merged.warnings == ["summary too long"]
    assert merged.checks_passed["llm_unsupported_claims"] is True


def test_format_overview_retry_feedback_empty_reasons() -> None:
    assert format_overview_retry_feedback([]) == ""


def test_format_overview_retry_feedback_includes_reasons() -> None:
    text = format_overview_retry_feedback(
        ["UNSUPPORTED_CLAIMS: headline overclaims voice recordings"]
    )
    assert "Your previous JSON response was rejected" in text
    assert "UNSUPPORTED_CLAIMS: headline overclaims voice recordings" in text
    assert text.startswith("\n\n")
