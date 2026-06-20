from src.utils.standard_terms import (
    TermMateriality,
    classify_term_materiality,
    filter_danger_strings,
    should_exclude_from_dangers,
    topic_signal_score,
)


def test_llm_label_takes_precedence() -> None:
    assert (
        classify_term_materiality(
            "Binding arbitration with class action waiver",
            label=TermMateriality.MATERIAL_RISK,
        )
        == TermMateriality.MATERIAL_RISK
    )
    assert (
        classify_term_materiality(
            "Company may sell your personal information",
            label=TermMateriality.STANDARD_INDUSTRY,
        )
        == TermMateriality.STANDARD_INDUSTRY
    )


def test_standard_industry_excluded_with_label() -> None:
    sample = "DMCA repeat infringer policy"
    assert (
        classify_term_materiality(sample, label=TermMateriality.STANDARD_INDUSTRY)
        == TermMateriality.STANDARD_INDUSTRY
    )
    assert (
        should_exclude_from_dangers(sample, materiality=TermMateriality.STANDARD_INDUSTRY) is True
    )
    assert (
        topic_signal_score(
            sample, category="dangers", materiality=TermMateriality.STANDARD_INDUSTRY
        )
        == 2
    )


def test_notable_excluded_with_label() -> None:
    sample = "Binding arbitration / class action waiver"
    assert (
        classify_term_materiality(sample, label=TermMateriality.NOTABLE) == TermMateriality.NOTABLE
    )
    assert should_exclude_from_dangers(sample, materiality=TermMateriality.NOTABLE) is True
    assert (
        topic_signal_score(
            sample, category="dispute_resolution", materiality=TermMateriality.NOTABLE
        )
        == 4
    )


def test_material_risks_stay_prominent_with_label() -> None:
    sample = "Company may sell your personal information to advertising partners"
    assert (
        classify_term_materiality(sample, label=TermMateriality.MATERIAL_RISK)
        == TermMateriality.MATERIAL_RISK
    )
    assert should_exclude_from_dangers(sample, materiality=TermMateriality.MATERIAL_RISK) is False
    assert (
        topic_signal_score(sample, category="dangers", materiality=TermMateriality.MATERIAL_RISK)
        == 8
    )


def test_unknown_text_defaults_to_material_risk_without_label() -> None:
    sample = "We may monetize your usage data with advertising partners"
    assert classify_term_materiality(sample) == TermMateriality.MATERIAL_RISK
    assert should_exclude_from_dangers(sample) is False


def test_filter_danger_strings_requires_labels() -> None:
    """Without LLM labels, unlabeled strings stay (conservative default)."""
    values = [
        "Repeat infringer account termination",
        "No cap on liability for user-generated content claims",
    ]
    assert filter_danger_strings(values) == values

    filtered = filter_danger_strings(
        [
            "Repeat infringer account termination",
            "Binding arbitration with class action waiver",
            "No cap on liability for user-generated content claims",
        ],
        labels={
            "Repeat infringer account termination": TermMateriality.STANDARD_INDUSTRY,
            "Binding arbitration with class action waiver": TermMateriality.NOTABLE,
        },
    )
    assert filtered == ["No cap on liability for user-generated content claims"]


def test_filter_danger_strings_respects_llm_labels() -> None:
    filtered = filter_danger_strings(
        [
            "Binding arbitration with class action waiver",
            "No cap on liability for user-generated content claims",
        ],
        labels={
            "Binding arbitration with class action waiver": TermMateriality.MATERIAL_RISK,
        },
    )
    assert filtered == [
        "Binding arbitration with class action waiver",
        "No cap on liability for user-generated content claims",
    ]


def test_is_material_risk_helper() -> None:
    from src.utils.standard_terms import is_material_risk

    assert (
        is_material_risk(
            "Company may sell your personal information", label=TermMateriality.MATERIAL_RISK
        )
        is True
    )
    assert (
        is_material_risk(
            "Binding arbitration with class action waiver", label=TermMateriality.NOTABLE
        )
        is False
    )
    assert (
        is_material_risk("DMCA repeat infringer policy", label=TermMateriality.STANDARD_INDUSTRY)
        is False
    )
