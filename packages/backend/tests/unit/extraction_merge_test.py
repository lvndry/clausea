"""Tests for v4 extraction merge functions and _clean_raw."""

from src.models.document import (
    Document,
    ExtractedAIUsage,
    ExtractedChildrenPolicy,
    ExtractedCookieTracker,
    ExtractedDataItem,
    ExtractedRetentionRule,
    ExtractedTextItem,
    ExtractedThirdPartyRecipient,
    PrivacySignals,
)
from src.services.extraction_service import (
    _AIUsage,
    _ChildrenPolicy,
    _clean_raw,
    _CookieTracker,
    _DataItem,
    _Item,
    _merge_ai_usage,
    _merge_children_policy,
    _merge_cookie_trackers,
    _merge_data_items,
    _merge_privacy_signals,
    _merge_retention_rules,
    _merge_text_items,
    _merge_third_parties,
    _PrivacySignals,
    _RetentionRule,
    _ThirdParty,
)

_DOC = Document(
    url="https://example.com/privacy",
    product_id="prod1",
    doc_type="privacy_policy",
    markdown="",
    text="We collect your email address. We retain data for 30 days.",
)
_HASH = "testhash"


# ── _merge_data_items ───────────────────────────────────────────────


class TestMergeDataItems:
    def test_basic_insert(self) -> None:
        acc: dict[str, ExtractedDataItem] = {}
        _merge_data_items(
            acc,
            [
                _DataItem(
                    data_type="Email address",
                    sensitivity="medium",
                    required="required",
                    quote="email address",
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        assert len(acc) == 1
        item = next(iter(acc.values()))
        assert item.data_type == "Email address"
        assert item.sensitivity == "medium"
        assert item.required == "required"
        assert len(item.evidence) == 1

    def test_deduplication_keeps_higher_sensitivity(self) -> None:
        acc: dict[str, ExtractedDataItem] = {}
        _merge_data_items(
            acc,
            [_DataItem(data_type="Email", sensitivity="low", required="optional", quote="email")],
            document=_DOC,
            content_hash=_HASH,
        )
        _merge_data_items(
            acc,
            [_DataItem(data_type="email", sensitivity="high", required="unclear", quote="email")],
            document=_DOC,
            content_hash=_HASH,
        )
        assert len(acc) == 1
        item = next(iter(acc.values()))
        assert item.sensitivity == "high"
        assert len(item.evidence) == 2

    def test_required_wins_over_unclear(self) -> None:
        acc: dict[str, ExtractedDataItem] = {}
        _merge_data_items(
            acc,
            [_DataItem(data_type="Phone", sensitivity="medium", required="unclear", quote="phone")],
            document=_DOC,
            content_hash=_HASH,
        )
        _merge_data_items(
            acc,
            [
                _DataItem(
                    data_type="phone", sensitivity="medium", required="required", quote="phone"
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        assert next(iter(acc.values())).required == "required"

    def test_empty_data_type_skipped(self) -> None:
        acc: dict[str, ExtractedDataItem] = {}
        _merge_data_items(
            acc,
            [_DataItem(data_type="", sensitivity="medium", required="unclear", quote="x")],
            document=_DOC,
            content_hash=_HASH,
        )
        assert len(acc) == 0

    def test_invalid_sensitivity_defaults_to_medium(self) -> None:
        acc: dict[str, ExtractedDataItem] = {}
        _merge_data_items(
            acc,
            [_DataItem(data_type="Name", sensitivity="extreme", required="unclear", quote="name")],
            document=_DOC,
            content_hash=_HASH,
        )
        assert next(iter(acc.values())).sensitivity == "medium"


# ── _merge_retention_rules ──────────────────────────────────────────


class TestMergeRetentionRules:
    def test_basic_insert(self) -> None:
        acc: dict[str, ExtractedRetentionRule] = {}
        _merge_retention_rules(
            acc,
            [
                _RetentionRule(
                    data_scope="Account data",
                    duration="30 days",
                    conditions="After deletion",
                    quote="30 days",
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        assert len(acc) == 1
        item = next(iter(acc.values()))
        assert item.data_scope == "Account data"
        assert item.duration == "30 days"

    def test_longer_duration_wins(self) -> None:
        acc: dict[str, ExtractedRetentionRule] = {}
        _merge_retention_rules(
            acc,
            [_RetentionRule(data_scope="Logs", duration="7 days", quote="7 days")],
            document=_DOC,
            content_hash=_HASH,
        )
        _merge_retention_rules(
            acc,
            [
                _RetentionRule(
                    data_scope="logs", duration="90 days after termination", quote="90 days"
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        assert next(iter(acc.values())).duration == "90 days after termination"


# ── _merge_cookie_trackers ──────────────────────────────────────────


class TestMergeCookieTrackers:
    def test_basic_insert(self) -> None:
        acc: dict[str, ExtractedCookieTracker] = {}
        _merge_cookie_trackers(
            acc,
            [
                _CookieTracker(
                    name_or_type="Google Analytics",
                    category="analytics",
                    third_party=True,
                    quote="GA",
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        assert len(acc) == 1
        item = next(iter(acc.values()))
        assert item.name_or_type == "Google Analytics"
        assert item.category == "analytics"
        assert item.third_party is True

    def test_third_party_true_wins(self) -> None:
        acc: dict[str, ExtractedCookieTracker] = {}
        _merge_cookie_trackers(
            acc,
            [
                _CookieTracker(
                    name_or_type="Pixel", category="advertising", third_party=False, quote="pixel"
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        _merge_cookie_trackers(
            acc,
            [
                _CookieTracker(
                    name_or_type="pixel", category="advertising", third_party=True, quote="pixel"
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        assert next(iter(acc.values())).third_party is True

    def test_invalid_category_defaults_to_other(self) -> None:
        acc: dict[str, ExtractedCookieTracker] = {}
        _merge_cookie_trackers(
            acc,
            [_CookieTracker(name_or_type="Custom", category="tracking", quote="custom")],
            document=_DOC,
            content_hash=_HASH,
        )
        assert next(iter(acc.values())).category == "other"


# ── _merge_third_parties ────────────────────────────────────────────


class TestMergeThirdParties:
    def test_accumulates_data_shared(self) -> None:
        acc: dict[str, ExtractedThirdPartyRecipient] = {}
        _merge_third_parties(
            acc,
            [
                _ThirdParty(
                    recipient="Advertisers",
                    data_shared=["email"],
                    purpose="Ads",
                    quote="advertisers",
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        _merge_third_parties(
            acc,
            [_ThirdParty(recipient="advertisers", data_shared=["location"], quote="advertisers")],
            document=_DOC,
            content_hash=_HASH,
        )
        assert len(acc) == 1
        item = next(iter(acc.values()))
        assert "email" in item.data_shared
        assert "location" in item.data_shared

    def test_longer_purpose_wins(self) -> None:
        acc: dict[str, ExtractedThirdPartyRecipient] = {}
        _merge_third_parties(
            acc,
            [_ThirdParty(recipient="Analytics", purpose="Stats", quote="x")],
            document=_DOC,
            content_hash=_HASH,
        )
        _merge_third_parties(
            acc,
            [
                _ThirdParty(
                    recipient="analytics", purpose="Usage statistics and performance", quote="x"
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        assert next(iter(acc.values())).purpose == "Usage statistics and performance"


# ── _merge_ai_usage ─────────────────────────────────────────────────


class TestMergeAIUsage:
    def test_basic_insert(self) -> None:
        acc: dict[str, ExtractedAIUsage] = {}
        _merge_ai_usage(
            acc,
            [
                _AIUsage(
                    usage_type="training_on_user_data",
                    description="User content trains models",
                    opt_out_available="yes",
                    opt_out_mechanism="Settings > Privacy",
                    quote="trains models",
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        assert len(acc) == 1
        item = next(iter(acc.values()))
        assert item.usage_type == "training_on_user_data"
        assert item.opt_out_available == "yes"

    def test_opt_out_yes_wins(self) -> None:
        acc: dict[str, ExtractedAIUsage] = {}
        _merge_ai_usage(
            acc,
            [
                _AIUsage(
                    usage_type="profiling",
                    description="User profiling",
                    opt_out_available="unclear",
                    quote="x",
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        _merge_ai_usage(
            acc,
            [
                _AIUsage(
                    usage_type="profiling",
                    description="User profiling",
                    opt_out_available="yes",
                    quote="x",
                )
            ],
            document=_DOC,
            content_hash=_HASH,
        )
        assert next(iter(acc.values())).opt_out_available == "yes"

    def test_invalid_usage_type_defaults_to_other(self) -> None:
        acc: dict[str, ExtractedAIUsage] = {}
        _merge_ai_usage(
            acc,
            [_AIUsage(usage_type="magic", description="Something", quote="x")],
            document=_DOC,
            content_hash=_HASH,
        )
        assert next(iter(acc.values())).usage_type == "other"


# ── _merge_children_policy ──────────────────────────────────────────


class TestMergeChildrenPolicy:
    def test_returns_none_when_no_data(self) -> None:
        result = _merge_children_policy(None, None, document=_DOC, content_hash=_HASH)
        assert result is None

    def test_creates_from_first_chunk(self) -> None:
        result = _merge_children_policy(
            None,
            _ChildrenPolicy(minimum_age=13, parental_consent_required=True, quote="under 13"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert result is not None
        assert result.minimum_age == 13
        assert result.parental_consent_required is True

    def test_higher_age_wins(self) -> None:
        acc = ExtractedChildrenPolicy(minimum_age=13, evidence=[])
        result = _merge_children_policy(
            acc,
            _ChildrenPolicy(minimum_age=16, quote="under 16"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert result is not None
        assert result.minimum_age == 16

    def test_parental_consent_true_wins(self) -> None:
        acc = ExtractedChildrenPolicy(parental_consent_required=False, evidence=[])
        result = _merge_children_policy(
            acc,
            _ChildrenPolicy(parental_consent_required=True, quote="parental consent"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert result is not None
        assert result.parental_consent_required is True


# ── _merge_privacy_signals ──────────────────────────────────────────


class TestMergePrivacySignals:
    def test_yes_wins_over_unclear(self) -> None:
        acc = PrivacySignals()
        _merge_privacy_signals(
            acc,
            _PrivacySignals(sells_data="yes", sells_data_quote="we sell data"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert acc.sells_data == "yes"

    def test_no_wins_over_unclear(self) -> None:
        acc = PrivacySignals()
        _merge_privacy_signals(
            acc,
            _PrivacySignals(sells_data="no", sells_data_quote="we do not sell"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert acc.sells_data == "no"

    def test_yes_wins_over_no(self) -> None:
        acc = PrivacySignals(sells_data="no")
        _merge_privacy_signals(
            acc,
            _PrivacySignals(sells_data="yes", sells_data_quote="we sell data"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert acc.sells_data == "yes"

    def test_self_service_wins_for_account_deletion(self) -> None:
        acc = PrivacySignals()
        _merge_privacy_signals(
            acc,
            _PrivacySignals(account_deletion="request_required", account_deletion_quote="email us"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert acc.account_deletion == "request_required"
        _merge_privacy_signals(
            acc,
            _PrivacySignals(
                account_deletion="self_service", account_deletion_quote="delete in settings"
            ),
            document=_DOC,
            content_hash=_HASH,
        )
        assert acc.account_deletion == "self_service"

    def test_consent_model_mixed_on_conflict(self) -> None:
        acc = PrivacySignals()
        _merge_privacy_signals(
            acc,
            _PrivacySignals(consent_model="opt_in", consent_model_quote="opt in"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert acc.consent_model == "opt_in"
        _merge_privacy_signals(
            acc,
            _PrivacySignals(consent_model="opt_out", consent_model_quote="opt out"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert acc.consent_model == "mixed"

    def test_null_signals_ignored(self) -> None:
        acc = PrivacySignals(sells_data="no")
        _merge_privacy_signals(acc, _PrivacySignals(), document=_DOC, content_hash=_HASH)
        assert acc.sells_data == "no"

    def test_breach_notification_yes_wins(self) -> None:
        acc = PrivacySignals()
        _merge_privacy_signals(
            acc,
            _PrivacySignals(breach_notification="no", breach_notification_quote="no notify"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert acc.breach_notification == "no"
        _merge_privacy_signals(
            acc,
            _PrivacySignals(breach_notification="yes", breach_notification_quote="we notify"),
            document=_DOC,
            content_hash=_HASH,
        )
        assert acc.breach_notification == "yes"


# ── _merge_text_items ───────────────────────────────────────────────


class TestMergeTextItems:
    def test_basic_merge(self) -> None:
        acc: dict[str, ExtractedTextItem] = {}
        _merge_text_items(
            acc,
            [_Item(value="Encryption at rest", quote="encryption at rest")],
            document=_DOC,
            content_hash=_HASH,
        )
        assert len(acc) == 1
        assert next(iter(acc.values())).value == "Encryption at rest"

    def test_deduplication(self) -> None:
        acc: dict[str, ExtractedTextItem] = {}
        _merge_text_items(
            acc,
            [_Item(value="TLS encryption", quote="tls")],
            document=_DOC,
            content_hash=_HASH,
        )
        _merge_text_items(
            acc,
            [_Item(value="tls encryption", quote="tls2")],
            document=_DOC,
            content_hash=_HASH,
        )
        assert len(acc) == 1
        assert len(next(iter(acc.values())).evidence) == 2


# ── _clean_raw ──────────────────────────────────────────────────────


class TestCleanRaw:
    def test_converts_non_standard_types_to_str(self) -> None:
        raw = {"items": [{"value": "test", "custom": object()}]}
        cleaned = _clean_raw(raw)
        assert isinstance(cleaned["items"][0]["custom"], str)

    def test_preserves_empty_lists(self) -> None:
        raw = {"items": [{"purposes": [], "value": "test"}]}
        cleaned = _clean_raw(raw)
        assert cleaned["items"][0]["purposes"] == []

    def test_preserves_normal_types(self) -> None:
        raw = {"items": [{"value": "x", "count": 5, "flag": True, "nested": {"a": 1}}]}
        cleaned = _clean_raw(raw)
        assert cleaned["items"][0]["count"] == 5
        assert cleaned["items"][0]["flag"] is True
        assert cleaned["items"][0]["nested"] == {"a": 1}

    def test_non_dict_passthrough(self) -> None:
        assert _clean_raw("not a dict") == "not a dict"  # type: ignore[arg-type]
