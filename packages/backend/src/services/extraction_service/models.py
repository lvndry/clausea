"""Pydantic models that define the expected JSON structure of each LLM extraction cluster.

**What it does**
Each model mirrors one section of the structured extraction prompt.  After the
LLM returns a JSON object for a document chunk, the response is parsed into
these models so the merge layer (``merging.py``) can accumulate results across
chunks in a type-safe way.

**What it contains**
- ``_PrivacySignals``: ``data_sharing``, ``data_collection``, ``data_retention``,
  ``user_rights``, ``policy_changes`` — each a yes/no/unclear with quote.
- ``_DataItem``: a single data category being collected/shared.
- ``_ThirdParty``: third-party recipient with purpose.
- ``_CookieTracker``: cookie/tracker name, category, purpose, duration.
- ``_RetentionRule``: data type + retention period.
- ``_AIUsage``: AI/automated decision-making disclosure.
- ``_ChildrenPolicy``: children's data handling statements.
- ``_Item``: generic (value, quote) pair used as a building block.

**What it prevents**
Unstructured dict access and key-name typos when handling LLM responses.
Pydantic validation catches missing fields and type mismatches at parse time.
"""

from pydantic import BaseModel, Field

from src.utils.coercion import LenientBool


class _Item(BaseModel):
    value: str
    quote: str
    materiality: str | None = None


class _DataItem(BaseModel):
    data_type: str
    sensitivity: str = "medium"
    required: str = "unclear"
    quote: str


class _PurposeLink(BaseModel):
    data_type: str
    purposes: list[str] = Field(default_factory=list)
    legal_basis: str | None = None
    quote: str


class _RetentionRule(BaseModel):
    data_scope: str
    duration: str
    conditions: str | None = None
    quote: str


class _CookieTracker(BaseModel):
    name_or_type: str
    category: str = "other"
    duration: str | None = None
    third_party: LenientBool = False
    opt_out_mechanism: str | None = None
    quote: str


class _ThirdParty(BaseModel):
    recipient: str
    data_shared: list[str] = Field(default_factory=list)
    purpose: str | None = None
    risk_level: str | None = None
    quote: str


class _InternationalTransfer(BaseModel):
    destination: str
    mechanism: str | None = None
    data_types: list[str] = Field(default_factory=list)
    quote: str


class _GovernmentAccess(BaseModel):
    authority_type: str
    conditions: str
    data_scope: str | None = None
    quote: str


class _CorporateFamily(BaseModel):
    entities: list[str] = Field(default_factory=list)
    data_shared: list[str] = Field(default_factory=list)
    purpose: str | None = None
    quote: str


class _UserRight(BaseModel):
    right_type: str
    description: str
    mechanism: str | None = None
    quote: str


class _AIUsage(BaseModel):
    usage_type: str
    description: str
    data_involved: list[str] = Field(default_factory=list)
    opt_out_available: str = "unclear"
    opt_out_mechanism: str | None = None
    consequences: str | None = None
    quote: str


class _ChildrenPolicy(BaseModel):
    minimum_age: int | None = None
    parental_consent_required: LenientBool = False
    special_protections: str | None = None
    quote: str | None = None


class _Liability(BaseModel):
    scope: str
    limitation_type: str
    description: str
    extends_beyond_product: LenientBool = False
    quote: str


class _DisputeResolution(BaseModel):
    mechanism: str
    class_action_waiver: LenientBool = False
    jury_trial_waiver: LenientBool = False
    venue: str | None = None
    governing_law: str | None = None
    description: str | None = None
    quote: str


class _ContentOwnership(BaseModel):
    ownership_type: str
    scope: str
    description: str
    quote: str


class _ScopeExpansion(BaseModel):
    scope_type: str
    description: str
    entities_affected: list[str] = Field(default_factory=list)
    quote: str


class _PrivacySignals(BaseModel):
    sells_data: str | None = None
    sells_data_quote: str | None = None
    cross_site_tracking: str | None = None
    cross_site_tracking_quote: str | None = None
    account_deletion: str | None = None
    account_deletion_quote: str | None = None
    data_retention_summary: str | None = None
    data_retention_quote: str | None = None
    consent_model: str | None = None
    consent_model_quote: str | None = None
    ai_training_on_user_data: str | None = None
    ai_training_quote: str | None = None
    breach_notification: str | None = None
    breach_notification_quote: str | None = None
    data_minimization: str | None = None
    data_minimization_quote: str | None = None
    children_data_collection: str | None = None
    children_data_collection_quote: str | None = None


class _ClusterDataPractices(BaseModel):
    data_collected: list[_DataItem] = Field(default_factory=list)
    data_purposes: list[_PurposeLink] = Field(default_factory=list)
    retention_policies: list[_RetentionRule] = Field(default_factory=list)
    security_measures: list[_Item] = Field(default_factory=list)
    cookies_and_trackers: list[_CookieTracker] = Field(default_factory=list)


class _ClusterSharingTransfers(BaseModel):
    third_party_details: list[_ThirdParty] = Field(default_factory=list)
    international_transfers: list[_InternationalTransfer] = Field(default_factory=list)
    government_access: list[_GovernmentAccess] = Field(default_factory=list)
    corporate_family_sharing: list[_CorporateFamily] = Field(default_factory=list)


class _ClusterRightsAI(BaseModel):
    user_rights: list[_UserRight] = Field(default_factory=list)
    consent_mechanisms: list[_Item] = Field(default_factory=list)
    account_lifecycle: list[_Item] = Field(default_factory=list)
    ai_usage: list[_AIUsage] = Field(default_factory=list)
    children_policy: _ChildrenPolicy | None = None
    privacy_signals: _PrivacySignals | None = None


class _ClusterLegalScope(BaseModel):
    liability: list[_Liability] = Field(default_factory=list)
    dispute_resolution: list[_DisputeResolution] = Field(default_factory=list)
    content_ownership: list[_ContentOwnership] = Field(default_factory=list)
    scope_expansion: list[_ScopeExpansion] = Field(default_factory=list)
    indemnification: list[_Item] = Field(default_factory=list)
    termination_consequences: list[_Item] = Field(default_factory=list)
    dangers: list[_Item] = Field(default_factory=list)
    benefits: list[_Item] = Field(default_factory=list)
    recommended_actions: list[_Item] = Field(default_factory=list)


__all__ = [
    "_AIUsage",
    "_ChildrenPolicy",
    "_ClusterDataPractices",
    "_ClusterLegalScope",
    "_ClusterRightsAI",
    "_ClusterSharingTransfers",
    "_ContentOwnership",
    "_CookieTracker",
    "_CorporateFamily",
    "_DataItem",
    "_DisputeResolution",
    "_GovernmentAccess",
    "_InternationalTransfer",
    "_Item",
    "_Liability",
    "_PrivacySignals",
    "_PurposeLink",
    "_RetentionRule",
    "_ScopeExpansion",
    "_ThirdParty",
    "_UserRight",
]
