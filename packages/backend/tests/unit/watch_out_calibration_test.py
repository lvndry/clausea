"""Unit tests for consumer watch-out severity calibration."""

from src.models.document import ConsumerCase, ConsumerExplainer
from src.services.watch_out_calibration import (
    calibrate_consumer_explainer,
    calibrate_watch_out_case,
    is_informational_dispute_term,
    is_standard_legal_mechanic,
)


def test_repeat_infringer_is_standard_mechanic() -> None:
    case = ConsumerCase(
        title="Account disabled for infringement",
        means_for_you="Your account may be disabled for repeated copyright infringement.",
        severity="critical",
        quote="repeat infringer policy",
    )
    assert is_standard_legal_mechanic(case) is True
    assert calibrate_watch_out_case(case) is None


def test_assignment_restriction_is_standard_mechanic() -> None:
    case = ConsumerCase(
        title="Cannot transfer account",
        means_for_you="You may not assign or transfer this agreement without consent.",
        severity="high",
    )
    assert is_standard_legal_mechanic(case) is True
    assert calibrate_watch_out_case(case) is None


def test_arbitration_downgrades_to_medium() -> None:
    case = ConsumerCase(
        title="Binding arbitration",
        means_for_you="You waive the right to sue in court or join a class action.",
        severity="critical",
        classification="blocker",
        quote="binding arbitration",
    )
    assert is_informational_dispute_term(case) is True
    adjusted = calibrate_watch_out_case(case)
    assert adjusted is not None
    assert adjusted.severity == "medium"
    assert adjusted.classification == "informational"


def test_data_sale_is_not_filtered() -> None:
    case = ConsumerCase(
        title="Sells your data",
        means_for_you="Advertisers may buy your personal information.",
        severity="critical",
        quote="sell your personal information",
    )
    assert is_standard_legal_mechanic(case) is False
    assert is_informational_dispute_term(case) is False
    adjusted = calibrate_watch_out_case(case)
    assert adjusted is not None
    assert adjusted.severity == "critical"


def test_calibrate_explainer_removes_boilerplate_and_downgrades_arbitration() -> None:
    explainer = ConsumerExplainer(
        grade="E",
        watch_out_for=[
            ConsumerCase(
                title="Repeat infringer",
                means_for_you="Accounts disabled for DMCA violations.",
                severity="critical",
            ),
            ConsumerCase(
                title="Class action waiver",
                means_for_you="Disputes must be resolved by arbitration.",
                severity="high",
            ),
            ConsumerCase(
                title="Sells data",
                means_for_you="They sell personal information to partners.",
                severity="critical",
            ),
        ],
    )

    calibrated = calibrate_consumer_explainer(explainer)

    assert len(calibrated.watch_out_for) == 2
    assert calibrated.watch_out_for[0].title == "Class action waiver"
    assert calibrated.watch_out_for[0].severity == "medium"
    assert calibrated.watch_out_for[1].title == "Sells data"
    assert calibrated.watch_out_for[1].severity == "critical"
