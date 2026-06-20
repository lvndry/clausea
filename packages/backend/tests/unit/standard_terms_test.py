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
