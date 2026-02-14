# Deep Analysis (Level 3) Specification

## Overview

Deep Analysis is Level 3 of Clausea's analysis hierarchy, designed for legal teams, compliance officers, and enterprise users who need comprehensive, detailed analysis of legal documents.

**Target Users:**

- Legal teams reviewing vendor contracts
- Compliance officers conducting audits
- Enterprise risk assessment teams
- Privacy professionals doing detailed reviews

**Use Case:** "I need to understand every clause, identify all risks, and have a complete picture for legal/compliance review"

## Analysis Levels Summary

- **Level 1 (Overview)**: Quick decision-making (<60 seconds) - "Should I use this service?"
- **Level 2 (Analysis)**: Comprehensive understanding (2-5 minutes) - "What are the key risks and benefits?"
- **Level 3 (Deep Analysis)**: Complete legal review (10-20 minutes) - "I need every detail for compliance/legal review"

## Deep Analysis Components

### 1. Document-by-Document Deep Breakdown

For each document, provide:

#### Document Header

- Document type, title, URL
- Effective date, last updated
- Locale and regions
- Document analysis summary

#### Critical Clauses Analysis

- **Data Collection Clauses**: Specific sections that describe data collection
  - Exact quotes from document
  - Line numbers or section references (if available)
  - Risk level and explanation
- **Data Sharing Clauses**: Third-party sharing provisions
  - Specific language about sharing/selling
  - Third-party categories mentioned
  - Opt-out mechanisms (or lack thereof)
- **User Rights Clauses**: Rights granted to users
  - Specific rights mentioned
  - How to exercise (with exact instructions from document)
  - Limitations or restrictions on rights
- **Liability & Indemnification Clauses** (for Terms of Service)

  - Indemnification provisions
  - Limitation of liability
  - Dispute resolution mechanisms
  - Governing law

- **Retention & Deletion Clauses**

  - Data retention periods
  - Deletion policies
  - Exceptions or limitations

- **Security & Breach Clauses**
  - Security measures described
  - Breach notification requirements
  - Security standards mentioned

#### Document-Specific Risk Assessment

- Risk score breakdown by category
- Top concerns specific to this document
- Positive protections specific to this document
- Missing information or unclear provisions

### 2. Cross-Document Analysis

#### Contradictions & Inconsistencies

- Where documents say different things
- Example: "Privacy Policy says data not sold, but Terms allow sharing with 'partners'"
- Impact assessment of contradictions

#### Information Gaps

- What's missing across all documents
- Example: "No clear data retention policy mentioned in any document"
- Risk implications of missing information

#### Document Relationships

- How documents reference each other
- Dependencies between documents
- Which document takes precedence (if stated)

### 3. Enhanced Compliance Analysis

For each applicable regulation (GDPR, CCPA, PIPEDA, LGPD, etc.):

#### Detailed Compliance Breakdown

- **Compliance Score**: 0-10 with justification
- **Status**: Compliant / Partially Compliant / Non-Compliant / Unknown
- **Strengths**: What the organization does well
- **Gaps**: Specific violations or missing requirements
- **Remediation Recommendations**: How to fix compliance issues

#### Regulation-Specific Analysis

- **GDPR**:
  - Lawful basis for processing
  - Data subject rights (access, erasure, portability, etc.)
  - Data transfer mechanisms
  - DPO requirements
  - Breach notification compliance
- **CCPA**:
  - Right to know implementation
  - Right to delete implementation
  - Opt-out mechanisms
  - "Do Not Sell" link presence
  - Non-discrimination provisions
- **PIPEDA**:

  - Consent mechanisms
  - Purpose limitation
  - Accuracy requirements
  - Safeguards described
  - Access rights

- **LGPD**:
  - Legal basis for processing
  - Data subject rights
  - DPO requirements
  - Security measures
  - Data breach notification

### 4. Legal & Business Context

#### Historical Changes (if available)

- Document version history
- Significant changes between versions
- Risk trend analysis (improving/worsening)

#### Business Impact Assessment

- **For Individual Users**:

  - Privacy risk level
  - Data exposure assessment
  - Recommended actions with priority

- **For Business Users**:
  - Liability exposure
  - Contract risk assessment
  - Vendor risk score
  - Business impact (financial, reputational, operational)

#### Risk Prioritization

- Critical risks (immediate action needed)
- High risks (address soon)
- Medium risks (monitor)
- Low risks (acceptable)

### 5. Full Document Access

- Complete document text (or key sections)
- Annotated sections with analysis notes
- Searchable document content
- Export capabilities (PDF, JSON)

## Data Model Structure

```python
class DocumentDeepAnalysis(BaseModel):
    """Deep analysis of a single document."""
    document_id: str
    document_type: DocType
    title: str | None
    url: str

    # Document metadata
    effective_date: datetime | None
    last_updated: datetime | None
    locale: str | None
    regions: list[Region]

    # Full analysis from Level 2
    analysis: DocumentAnalysis

    # Deep analysis additions
    critical_clauses: list[CriticalClause]
    document_risk_breakdown: DocumentRiskBreakdown
    key_sections: list[DocumentSection]  # Important sections with quotes

class CriticalClause(BaseModel):
    """Analysis of a critical clause in a document."""
    clause_type: Literal[
        "data_collection",
        "data_sharing",
        "user_rights",
        "liability",
        "indemnification",
        "retention",
        "deletion",
        "security",
        "breach_notification",
        "dispute_resolution",
        "governing_law"
    ]
    section_title: str | None  # "Section 3: Data Collection"
    quote: str  # Exact text from document
    risk_level: Literal["low", "medium", "high", "critical"]
    analysis: str  # Explanation of what this means
    compliance_impact: list[str]  # Which regulations this affects

class DocumentSection(BaseModel):
    """Important section of a document with analysis."""
    section_title: str
    content: str  # Full text of section
    importance: Literal["low", "medium", "high", "critical"]
    analysis: str  # What this section means
    related_clauses: list[str]  # IDs of related critical clauses

class DocumentRiskBreakdown(BaseModel):
    """Detailed risk assessment for a document."""
    overall_risk: int  # 0-10
    risk_by_category: dict[str, int]  # {"data_sharing": 8, "retention": 5}
    top_concerns: list[str]  # Specific concerns
    positive_protections: list[str]  # Good practices
    missing_information: list[str]  # What's not mentioned

class CrossDocumentAnalysis(BaseModel):
    """Analysis across all documents."""
    contradictions: list[DocumentContradiction]
    information_gaps: list[str]
    document_relationships: list[DocumentRelationship]

class DocumentContradiction(BaseModel):
    """Identified contradiction between documents."""
    document_a: str  # Document ID or name
    document_b: str
    contradiction_type: str  # "data_sharing", "retention", etc.
    description: str  # What contradicts
    document_a_statement: str  # What document A says
    document_b_statement: str  # What document B says
    impact: str  # Risk/legal impact
    recommendation: str  # How to resolve

class EnhancedComplianceBreakdown(BaseModel):
    """Enhanced compliance analysis per regulation."""
    regulation: str  # "GDPR", "CCPA", etc.
    score: int  # 0-10
    status: Literal["Compliant", "Partially Compliant", "Non-Compliant", "Unknown"]
    strengths: list[str]
    gaps: list[str]
    violations: list[ComplianceViolation]  # Specific violations
    remediation_recommendations: list[str]
    detailed_analysis: str  # Comprehensive explanation

class ComplianceViolation(BaseModel):
    """Specific compliance violation."""
    requirement: str  # "GDPR Article 15 - Right of access"
    violation_type: Literal["missing", "unclear", "non_compliant"]
    description: str  # What's wrong
    severity: Literal["low", "medium", "high", "critical"]
    remediation: str  # How to fix

class CompanyDeepAnalysis(BaseModel):
    """Level 3: Deep analysis for legal/compliance review."""
    # Include Level 2
    analysis: CompanyAnalysis

    # Document-by-document deep breakdown
    document_analyses: list[DocumentDeepAnalysis]

    # Cross-document analysis
    cross_document_analysis: CrossDocumentAnalysis

    # Enhanced compliance
    enhanced_compliance: dict[str, EnhancedComplianceBreakdown]  # By regulation

    # Business context
    business_impact: BusinessImpactAssessment
    risk_prioritization: RiskPrioritization

    # Historical context (if available)
    change_history: list[DocumentChange] | None = None

class BusinessImpactAssessment(BaseModel):
    """Business impact assessment."""
    for_individuals: IndividualImpact
    for_businesses: BusinessImpact

class IndividualImpact(BaseModel):
    """Privacy impact for individual users."""
    privacy_risk_level: Literal["low", "medium", "high", "critical"]
    data_exposure_summary: str
    recommended_actions: list[PrioritizedAction]

class BusinessImpact(BaseModel):
    """Business impact for enterprise users."""
    liability_exposure: int  # 0-10
    contract_risk_score: int  # 0-10
    vendor_risk_score: int  # 0-10
    financial_impact: str  # Potential financial consequences
    reputational_risk: str  # Reputational implications
    operational_risk: str  # Operational implications
    recommended_actions: list[PrioritizedAction]

class PrioritizedAction(BaseModel):
    """Action item with priority."""
    action: str
    priority: Literal["critical", "high", "medium", "low"]
    rationale: str
    deadline: str | None  # "Immediate", "Within 30 days", etc.

class RiskPrioritization(BaseModel):
    """Prioritized list of risks."""
    critical: list[str]
    high: list[str]
    medium: list[str]
    low: list[str]
```

## Implementation Strategy

### Phase 1: Data Model & Basic Structure

1. Define all Pydantic models in `document.py`
2. Create basic deep analysis generation function
3. Add route endpoint

### Phase 2: LLM Prompt Engineering

1. Create deep analysis prompt that:
   - Analyzes each document in detail
   - Identifies critical clauses with quotes
   - Finds contradictions across documents
   - Performs enhanced compliance analysis
   - Assesses business impact

### Phase 3: Service Implementation

1. Implement `generate_company_deep_analysis()` in summarizer
2. Add caching strategy (similar to meta-summary)
3. Add service method in `company_service.py`

### Phase 4: API & Frontend

1. Add `/products/{slug}/deep-analysis` route
2. Update frontend to display deep analysis
3. Add document viewer with annotations
4. Add export functionality

## Performance Considerations

- **Generation Time**: Deep analysis may take 30-60 seconds for products with multiple documents
- **Caching**: Cache deep analysis results (invalidate when documents change)
- **Async Processing**: Consider async generation with status updates for large analyses
- **Token Usage**: Deep analysis will use more LLM tokens - optimize prompts and use appropriate models

## Cost Optimization

- Use GPT-4o for complex legal reasoning in deep analysis
- Cache results aggressively
- Only generate on-demand (not automatically)
- Consider tier-based access (Enterprise only?)

## Success Criteria

- Legal teams can conduct complete reviews using deep analysis
- Compliance officers can identify all gaps and violations
- Enterprise users can assess vendor risk comprehensively
- All critical clauses are identified and explained
- Cross-document contradictions are clearly highlighted
- Compliance analysis is actionable with remediation steps
