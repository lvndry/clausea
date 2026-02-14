"""Prompts for compliance checking."""

COMPLIANCE_CHECK_JSON_SCHEMA = """{
  "regulation": string,
  "status": "Compliant" | "Partially Compliant" | "Non-Compliant" | "Unknown",
  "score": int (0-10),
  "strengths": [string],
  "gaps": [string],
  "limitations": [string] | null,
  "evidence": [
    {"source_id": string, "quote": string, "requirement": string}
  ] | null
}"""

COMPLIANCE_CHECK_PROMPT = """Regulation: {regulation}

Context (multiple excerpts, each labeled SOURCE[...] with url + offsets):
{context}

Task:
- Assess compliance with {regulation} using ONLY the provided context.
- If the context does not contain enough information, set status="Unknown" and list missing items in limitations.
- Do not infer beyond the text.

Output JSON matching this schema:
{schema}
"""
