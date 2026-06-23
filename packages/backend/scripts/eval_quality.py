"""Dump the analysed documents + product overview for a slug, for manual quality review.

Usage:
    uv run python scripts/eval_quality.py <slug>
"""

from __future__ import annotations

import sys

from src.core.database import db_session
from src.core.logging import setup_logging
from src.services.service_factory import create_document_service, create_product_service


def _line(char: str = "-", n: int = 80) -> None:
    print(char * n)


async def main(slug: str) -> None:
    setup_logging()
    product_svc = create_product_service()
    doc_svc = create_document_service()

    async with db_session() as db:
        product = await product_svc.get_product_by_slug(db, slug)
        if not product:
            print(f"No product for slug={slug}")
            return

        _line("=")
        print(f"PRODUCT: {product.name}  (slug={product.slug}, id={product.id})")
        print(f"domains: {product.domains}")
        _line("=")

        docs = await doc_svc.get_product_documents(db, product.id)
        print(f"\nDOCUMENTS: {len(docs)}\n")
        for d in docs:
            a = d.analysis
            print(f"### [{d.doc_type}] {d.title or '(no title)'}")
            print(f"    url: {d.url}")
            print(f"    locale={d.locale} regions={d.regions} effective_date={d.effective_date}")
            print(f"    markdown_len={len(d.markdown or '')}")
            if a:
                print(f"    verdict={a.verdict} risk_score={a.risk_score}")
                if a.scores:
                    sc = ", ".join(f"{k}={v.score}" for k, v in a.scores.items())
                    print(f"    scores: {sc}")
                print(f"    summary: {(a.summary or '')[:400]}")
                if a.keypoints:
                    print("    keypoints:")
                    for kp in a.keypoints[:6]:
                        print(f"      - {kp}")
                if a.compliance_status:
                    print(f"    compliance: {a.compliance_status}")
                if a.critical_clauses:
                    print(f"    critical_clauses: {len(a.critical_clauses)}")
                    for cc in a.critical_clauses[:3]:
                        title = getattr(cc, "title", None) or getattr(cc, "clause", "")
                        print(f"      - {str(title)[:120]}")
            else:
                print("    (no analysis)")
            print()

        _line("=")
        print("PRODUCT OVERVIEW")
        _line("=")
        overview = await product_svc.get_product_overview(db, slug, product=product)
        if not overview:
            print("(no overview generated)")
            return

        o = overview
        print(f"product_name : {o.product_name}")
        print(f"verdict      : {o.verdict}")
        print(f"risk_score   : {o.risk_score}")
        print(f"one_line     : {o.one_line_summary}")
        if o.detailed_scores:
            print("detailed_scores:")
            ds_dict = (
                o.detailed_scores
                if isinstance(o.detailed_scores, dict)
                else o.detailed_scores.model_dump()
            )
            for dim, ds in ds_dict.items():
                score = ds.get("score") if isinstance(ds, dict) else ds
                print(f"  {dim}: {score}")
        print(f"\nkeypoints ({len(o.keypoints or [])}):")
        for kp in (o.keypoints or [])[:10]:
            print(f"  - {kp}")
        print(f"\ndata_collected ({len(o.data_collected or [])}): {o.data_collected}")
        print(f"\ndata_collection_details ({len(o.data_collection_details or [])}):")
        for dl in (o.data_collection_details or [])[:10]:
            print(f"  - {dl.data_type}: {dl.purposes}")
        print(f"\nthird_party_details ({len(o.third_party_details or [])}):")
        for tp in (o.third_party_details or [])[:10]:
            print(
                f"  - {tp.recipient} [{tp.risk_level}] shares={tp.data_shared} purpose={tp.purpose}"
            )
        print(f"\ndangers ({len(o.dangers or [])}):")
        for dg in (o.dangers or [])[:8]:
            print(f"  - {dg}")
        print(f"\nyour_rights ({len(o.your_rights or [])}):")
        for r in (o.your_rights or [])[:8]:
            print(f"  - {r}")
        if o.privacy_signals:
            ps = o.privacy_signals
            print("\nprivacy_signals:")
            print(f"  sells_data={ps.sells_data} cross_site_tracking={ps.cross_site_tracking}")
            print(f"  account_deletion={ps.account_deletion} consent_model={ps.consent_model}")
            print(f"  data_retention_summary={ps.data_retention_summary}")
        if o.compliance_status:
            print(f"\ncompliance_status: {o.compliance_status}")
        if o.coverage:
            print(f"\ncoverage ({len(o.coverage)}):")
            for c in o.coverage:
                print(f"  - {c.category}: {c.status}")
        if o.contract_clauses:
            print(f"\ncontract_clauses ({len(o.contract_clauses)}):")
            for cc in o.contract_clauses[:6]:
                print(f"  - {cc[:160]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: eval_quality.py <slug>")
        sys.exit(1)
    import asyncio

    asyncio.run(main(sys.argv[1]))
