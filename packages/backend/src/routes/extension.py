"""Extension routes for browser extension integration.

Provides lightweight endpoints optimized for the browser extension popup.
"""

from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import AnyHttpUrl, BaseModel

from src.core.database import get_db
from src.core.logging import get_logger
from src.services.email_service import EmailServiceError, get_email_service
from src.services.service_factory import create_product_service

logger = get_logger(__name__)

router = APIRouter(prefix="/extension", tags=["extension"])


class ExtensionCheckResponse(BaseModel):
    """Lightweight response for browser extension popup."""

    found: bool
    slug: str | None = None
    product_name: str | None = None
    verdict: (
        Literal["very_user_friendly", "user_friendly", "moderate", "pervasive", "very_pervasive"]
        | None
    ) = None
    risk_score: int | None = None
    one_line_summary: str | None = None
    top_concerns: list[str] | None = None
    # For the extension to know where to redirect
    analysis_url: str | None = None


class ExtensionRequestSupportPayload(BaseModel):
    """Payload for requesting Clausea to index a new site."""

    url: AnyHttpUrl
    source: Literal["browser_extension"] = "browser_extension"


class ExtensionRequestSupportResponse(BaseModel):
    success: bool


def extract_domain(url: str) -> str:
    """Extract the root domain from a URL.

    Examples:
        https://www.netflix.com/signup -> netflix.com
        https://app.slack.com/client -> slack.com
        https://zoom.us/join -> zoom.us
    """
    parsed = urlparse(url)
    hostname = parsed.netloc or parsed.path

    # Remove www. prefix
    if hostname.startswith("www."):
        hostname = hostname[4:]

    # Handle subdomains - keep only last two parts for most TLDs
    # But handle special cases like .co.uk, .com.au
    parts = hostname.split(".")

    # Common two-part TLDs
    two_part_tlds = {"co.uk", "com.au", "co.nz", "co.jp", "com.br", "co.in"}

    if len(parts) >= 3:
        potential_tld = ".".join(parts[-2:])
        if potential_tld in two_part_tlds:
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])

    return hostname


@router.get("/check", response_model=ExtensionCheckResponse)
async def check_url(
    url: str = Query(..., description="The URL to check (e.g., https://netflix.com/signup)"),
) -> ExtensionCheckResponse:
    """Check if we have privacy analysis for a given URL.

    This endpoint is optimized for browser extension use:
    - Fast response time (no JIT generation)
    - Lightweight payload
    - CORS-friendly

    The extension uses this to:
    1. Light up the icon (green/yellow/red) based on verdict
    2. Show a quick summary in the popup
    3. Link to the full analysis on clausea.co
    """
    domain = extract_domain(url)
    logger.debug(f"Extension check for URL: {url} -> domain: {domain}")

    async with get_db() as db:
        service = create_product_service()

        # Try to find product by domain
        product = await service.get_product_by_domain(db, domain)

        if not product:
            # Try without subdomain variations
            # e.g., if domain is "app.notion.so", try "notion.so"
            parts = domain.split(".")
            if len(parts) > 2:
                base_domain = ".".join(parts[-2:])
                product = await service.get_product_by_domain(db, base_domain)

        if not product:
            return ExtensionCheckResponse(found=False)

        # Get the overview if available
        overview = await service.get_product_overview(db, product.slug)

        if not overview:
            # Product exists but no analysis yet
            return ExtensionCheckResponse(
                found=True,
                slug=product.slug,
                product_name=product.name,
                analysis_url=f"https://clausea.co/products/{product.slug}",
            )

        # Extract top 3 concerns from dangers or keypoints
        top_concerns = None
        if overview.dangers:
            top_concerns = overview.dangers[:3]
        elif overview.keypoints:
            # Filter for concerning keypoints (heuristic: contains risk words)
            risk_keywords = ["share", "sell", "track", "collect", "third", "advertis", "retain"]
            concerning = [
                kp for kp in overview.keypoints if any(word in kp.lower() for word in risk_keywords)
            ]
            top_concerns = concerning[:3] if concerning else overview.keypoints[:3]

        return ExtensionCheckResponse(
            found=True,
            slug=product.slug,
            product_name=overview.product_name,
            verdict=overview.verdict,
            risk_score=overview.risk_score,
            one_line_summary=overview.one_line_summary,
            top_concerns=top_concerns,
            analysis_url=f"https://clausea.co/products/{product.slug}",
        )


@router.get("/domains", response_model=list[str])
async def get_supported_domains() -> list[str]:
    """Get list of all domains we have analysis for.

    The extension can use this to:
    1. Pre-cache which domains to watch for
    2. Show "X domains protected" in the popup
    """
    async with get_db() as db:
        service = create_product_service()
        products = await service.get_products_with_documents(db)

        domains = []
        for product in products:
            if product.domains:
                domains.extend(product.domains)

        return list(set(domains))


@router.post("/request-support", response_model=ExtensionRequestSupportResponse)
async def request_support(
    payload: ExtensionRequestSupportPayload,
    request: Request,
) -> ExtensionRequestSupportResponse:
    """Allow users to request Clausea to index a new website."""

    domain = extract_domain(str(payload.url))
    logger.info(
        "extension support request",
        domain=domain,
        url=str(payload.url),
        source=payload.source,
        ip=request.client.host if request.client else None,
    )

    email_service = get_email_service()
    metadata = {
        "ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
    }

    try:
        await email_service.send_support_request(
            domain=domain,
            url=str(payload.url),
            source=payload.source,
            metadata=metadata,
        )
    except EmailServiceError as error:
        logger.exception("failed to send support request email", domain=domain)
        raise HTTPException(status_code=500, detail=str(error)) from error

    return ExtensionRequestSupportResponse(success=True)
