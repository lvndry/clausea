from src.utils.standard_terms import (
    TermMateriality,
    classify_term_materiality,
    filter_danger_strings,
    should_exclude_from_dangers,
    topic_signal_score,
)


def test_standard_industry_terms_excluded_from_dangers() -> None:
    samples = [
        "Repeat infringer account termination (DMCA-normal)",
        "Non-assignable agreement clause",
        "DMCA repeat infringer policy",
        "This agreement may not be assigned without prior written consent",
    ]
    for sample in samples:
        assert classify_term_materiality(sample) == TermMateriality.STANDARD_INDUSTRY
        assert should_exclude_from_dangers(sample) is True
        assert topic_signal_score(sample, category="dangers") == 2


def test_arbitration_is_notable_not_danger() -> None:
    sample = "Binding arbitration / class action waiver"
    assert classify_term_materiality(sample) == TermMateriality.NOTABLE
    assert should_exclude_from_dangers(sample) is True
    assert topic_signal_score(sample, category="dispute_resolution") == 4
    assert topic_signal_score(sample, category="dangers") == 4


def test_material_risks_stay_prominent() -> None:
    sample = "Company may sell your personal information to advertising partners"
    assert classify_term_materiality(sample) == TermMateriality.MATERIAL_RISK
    assert should_exclude_from_dangers(sample) is False
    assert topic_signal_score(sample, category="dangers") == 8


def test_filter_danger_strings_drops_routine_boilerplate() -> None:
    filtered = filter_danger_strings(
        [
            "Repeat infringer account termination",
            "Binding arbitration with class action waiver",
            "No cap on liability for user-generated content claims",
        ]
    )
    assert filtered == ["No cap on liability for user-generated content claims"]


def test_material_risk_patterns_cover_watch_out_edge_cases() -> None:
    """Patterns formerly duplicated in watch_out_calibration must classify here."""
    material_samples = [
        "We may monetize your usage data with advertising partners",
        "Content may be used for AI training and model training",
        "You grant a perpetual license to your uploads",
        "An irrevocable license to use your photos worldwide",
        "Sublicensable rights to your content",
        "You must indemnify us for any claims",
        "Automatic renewal unless cancelled 30 days prior",
        "Hidden fees may apply after the trial period",
        "We collect GPS coordinates for location services",
        "Services not intended for children under 13",
        "Cross-site tracking across third-party websites",
        "We indefinitely retain your account data",
        "No opt-out available for this data collection",
        "You cannot delete your biometric data once submitted",
        "Sale of personal information to data brokers",
    ]
    for sample in material_samples:
        assert classify_term_materiality(sample) == TermMateriality.MATERIAL_RISK, sample
        assert should_exclude_from_dangers(sample) is False


def test_standard_terms_not_overridden_by_broad_material_patterns() -> None:
    """Routine boilerplate must stay standard even when text mentions adjacent topics."""
    samples = [
        "Repeat infringer account termination under DMCA",
        "This agreement may not be assigned without prior written consent",
        "Binding arbitration with class action waiver",
    ]
    for sample in samples:
        assert classify_term_materiality(sample) != TermMateriality.MATERIAL_RISK, sample


def test_is_material_risk_helper() -> None:
    from src.utils.standard_terms import is_material_risk

    assert is_material_risk("Company may sell your personal information") is True
    assert is_material_risk("Binding arbitration with class action waiver") is False
    assert is_material_risk("DMCA repeat infringer policy") is False
