from src.analyzers.overview_guards import (
    OverviewValidationResult,
    check_actions_actionable,
    check_dangers_benefits_balance,
    check_e_grade_on_silence,
    check_generic_headline_opener,
    check_jargon,
    check_rights_have_paths,
    find_internal_state_language,
    find_long_sentences,
    find_unsupported_strong_claims,
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


def test_find_internal_state_language_clean_text() -> None:
    assert find_internal_state_language("Coinbase shares data with advertisers.") == []


def test_find_internal_state_language_detects_phrases() -> None:
    text = "Based on the extraction of the document and the policy bundle we conclude."
    hits = find_internal_state_language(text)
    assert "the extraction" in hits
    assert "the document" in hits
    assert "the policy bundle" in hits


def test_find_internal_state_language_case_insensitive() -> None:
    assert find_internal_state_language("The Provided Documents say little.") == [
        "the provided documents"
    ]


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


def test_find_unsupported_strong_claims_coinbase_case() -> None:
    headline = "Coinbase sells user identifiers to advertisers like Meta"
    summary = "Coinbase shares identifiers for advertising."
    citations = [{"quote": "we share identifiers for advertising", "verified": True}]
    privacy_signals = {"sells_data": "unclear"}
    unsupported = find_unsupported_strong_claims(headline, summary, citations, privacy_signals)
    assert "sells user" in unsupported


def test_find_unsupported_strong_claims_supported_by_signal() -> None:
    headline = "Spotify sells your listening history to advertisers."
    summary = ""
    citations = []
    privacy_signals = {"sells_data": "yes"}
    assert find_unsupported_strong_claims(headline, summary, citations, privacy_signals) == []


def test_find_unsupported_strong_claims_supported_by_verified_quote() -> None:
    headline = "App collects biometric data from face scans."
    summary = ""
    citations = [{"quote": "we collect biometric face scan data", "verified": True}]
    privacy_signals = None
    assert find_unsupported_strong_claims(headline, summary, citations, privacy_signals) == []


def test_find_unsupported_strong_claims_ignores_unverified_citations() -> None:
    headline = "App collects biometric data from face scans."
    summary = ""
    citations = [{"quote": "we collect biometric face scan data", "verified": False}]
    privacy_signals = None
    assert "biometric" in find_unsupported_strong_claims(
        headline, summary, citations, privacy_signals
    )


def test_find_unsupported_strong_claims_no_strong_phrases() -> None:
    headline = "Coinbase offers a self-service deletion path."
    summary = "Account deletion is available in settings."
    assert find_unsupported_strong_claims(headline, summary, [], None) == []


def test_find_unsupported_strong_claims_regex_patterns() -> None:
    headline = "Service retains your data indefinitely after deletion."
    summary = ""
    assert "retains.*indefinitely" in find_unsupported_strong_claims(headline, summary, [], None)


def test_check_dangers_benefits_balance_few_dangers_ok() -> None:
    assert check_dangers_benefits_balance(["a", "b"], [], "anything") is True


def test_check_dangers_benefits_balance_enough_benefits_ok() -> None:
    dangers = ["d"] * 5
    benefits = ["b1", "b2"]
    assert check_dangers_benefits_balance(dangers, benefits, "no ack") is True


def test_check_dangers_benefits_balance_imbalance_without_ack_fails() -> None:
    dangers = ["d"] * 6
    benefits = ["only one"]
    assert (
        check_dangers_benefits_balance(dangers, benefits, "The product is broadly risky.") is False
    )


def test_check_dangers_benefits_balance_imbalance_with_ack_passes() -> None:
    dangers = ["d"] * 6
    benefits = ["only one"]
    assert (
        check_dangers_benefits_balance(dangers, benefits, "The documents describe few protections.")
        is True
    )


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


def test_check_jargon_clean_text() -> None:
    assert check_jargon("The policy is clear and uses plain language.") is True


def test_check_jargon_over_limit_fails() -> None:
    text = "notwithstanding herein therein hereto the data processor indemnification clause"
    assert check_jargon(text) is False


def test_check_jargon_at_limit_passes() -> None:
    text = "notwithstanding herein therein the policy"
    assert check_jargon(text, max_hits=3) is True


def test_check_generic_headline_opener_specific_passes() -> None:
    assert (
        check_generic_headline_opener("Coinbase sells user identifiers to advertisers like Meta.")
        is True
    )


def test_check_generic_headline_opener_generic_fails() -> None:
    assert (
        check_generic_headline_opener(
            "This product collects extensive personal and behavioral data from users."
        )
        is False
    )


def test_check_generic_headline_opener_shares_pattern_fails() -> None:
    assert (
        check_generic_headline_opener(
            "The service shares your data with many advertising partners."
        )
        is False
    )


def test_check_generic_headline_opener_empty_passes() -> None:
    assert check_generic_headline_opener("") is True


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
            "Opt out in account settings",
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


def test_validate_overview_unsupported_strong_claim_re_rolls() -> None:
    overview = {
        "summary": "Coinbase shares identifiers for advertising.",
        "headline_claim": "Coinbase sells user identifiers to advertisers like Meta.",
        "grade": "D",
        "grade_justification": "Broad sharing with advertisers.",
        "privacy_signals": {"sells_data": "unclear"},
        "topic_stances": [
            {
                "status": "found",
                "evidence_count": 1,
                "supporting_citations": [
                    {"quote": "we share identifiers for advertising", "verified": True}
                ],
            },
        ],
    }
    result = validate_overview(overview, has_adequate_evidence=True)
    assert result.should_re_roll is True
    assert result.checks_passed["no_unsupported_strong_claims"] is False
    assert any("Strong claims" in r for r in result.re_roll_reasons)


def test_validate_overview_internal_state_language_re_rolls() -> None:
    overview = {
        "summary": "Based on the document the product is broadly risky.",
        "headline_claim": "Service collects extensive data.",
        "grade": "D",
        "grade_justification": "The extraction shows broad collection.",
        "topic_stances": [],
    }
    result = validate_overview(overview, has_adequate_evidence=True)
    assert result.should_re_roll is True
    assert result.checks_passed["no_internal_state_language"] is False


def test_validate_overview_warnings_for_medium_issues() -> None:
    long_summary = " ".join(["word"] * 25)
    long_sentence = " ".join(["word"] * 40)
    overview = {
        "summary": long_summary,
        "headline_claim": "Service collects a wide variety of personal data from users.",
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
    assert result.checks_passed["headline_opener_specific"] is False
    assert result.checks_passed["dangers_benefits_balance"] is False
    assert result.checks_passed["rights_have_paths"] is False
    assert result.checks_passed["actions_actionable"] is False
    assert result.checks_passed["no_long_sentences"] is False
    assert any("Summary exceeds" in w for w in result.warnings)
    assert any("Headline opener is generic" in w for w in result.warnings)


def test_validate_overview_jargon_warning() -> None:
    overview = {
        "summary": "notwithstanding herein therein hereto the policy is dense.",
        "headline_claim": "Service uses a data processor under standard contractual clauses.",
        "grade": "D",
        "grade_justification": "notwithstanding inter alia the indemnification is broad.",
        "topic_stances": [],
    }
    result = validate_overview(overview, has_adequate_evidence=True)
    assert result.checks_passed["no_jargon"] is False
    assert any("jargon" in w for w in result.warnings)


def test_validate_overview_gathers_citations_from_topic_stances() -> None:
    overview = {
        "summary": "Service sells your data to brokers.",
        "headline_claim": "Service sells your data to brokers.",
        "grade": "D",
        "grade_justification": "Data sale is documented.",
        "privacy_signals": {"sells_data": "unclear"},
        "topic_stances": [
            {
                "status": "found",
                "evidence_count": 1,
                "supporting_citations": [
                    {"quote": "we may sell your data to data brokers", "verified": True}
                ],
            },
        ],
    }
    result = validate_overview(overview, has_adequate_evidence=True)
    assert result.checks_passed["no_unsupported_strong_claims"] is True
