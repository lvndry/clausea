import json

from src.services.extraction_service import _extraction_validator


def test_extraction_validator_passes_valid_data_practices() -> None:
    content = json.dumps(
        {
            "data_collected": [{"label": "email", "evidence": "we collect email"}],
            "data_purposes": [],
            "retention_policies": [],
            "security_measures": [],
            "cookies_and_trackers": [],
        }
    )
    assert _extraction_validator("data_practices")(content) is True


def test_extraction_validator_fails_on_invalid_json() -> None:
    assert _extraction_validator("data_practices")("not json") is False


def test_extraction_validator_fails_when_all_lists_empty() -> None:
    content = json.dumps(
        {
            "data_collected": [],
            "data_purposes": [],
            "retention_policies": [],
            "security_measures": [],
            "cookies_and_trackers": [],
        }
    )
    assert _extraction_validator("data_practices")(content) is False


def test_extraction_validator_fails_missing_required_keys() -> None:
    content = json.dumps({"some_other_key": [{"label": "foo"}]})
    assert _extraction_validator("data_practices")(content) is False


def test_extraction_validator_passes_valid_sharing_transfers() -> None:
    content = json.dumps(
        {
            "third_party_details": [{"name": "Google", "evidence": "shared with Google"}],
            "international_transfers": [],
            "government_access": [],
            "corporate_family_sharing": [],
        }
    )
    assert _extraction_validator("sharing_transfers")(content) is True


def test_extraction_validator_passes_valid_rights_ai() -> None:
    content = json.dumps(
        {
            "user_rights": [{"right_type": "access", "evidence": "you may access"}],
            "consent_mechanisms": [],
            "account_lifecycle": [],
            "ai_usage": [],
        }
    )
    assert _extraction_validator("rights_ai")(content) is True


def test_extraction_validator_passes_valid_legal_scope() -> None:
    content = json.dumps(
        {
            "liability": [{"limitation": "no liability", "evidence": "..."}],
            "dispute_resolution": [],
            "content_ownership": [],
            "scope_expansion": [],
            "indemnification": [],
            "termination_consequences": [],
            "dangers": [],
            "benefits": [],
            "recommended_actions": [],
        }
    )
    assert _extraction_validator("legal_scope")(content) is True


def test_extraction_validator_unknown_cluster_accepts_any_non_empty_json() -> None:
    content = json.dumps({"anything": [1, 2, 3]})
    assert _extraction_validator("unknown_cluster")(content) is True


def test_extraction_validator_fails_on_non_dict_json() -> None:
    assert _extraction_validator("data_practices")("[]") is False
    assert _extraction_validator("data_practices")('"a string"') is False
    assert _extraction_validator("data_practices")("42") is False
