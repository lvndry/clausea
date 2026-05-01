"""Shared domain extraction utilities.

Uses ``tldextract`` with a bundled public suffix list to avoid network
fetches on the hot path.  Every module that needs to derive a root domain
from a URL should import ``extract_domain`` from here.
"""

from __future__ import annotations

import tldextract

_TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())


def extract_domain(url: str) -> str:
    """Extract the root domain from a URL.

    Examples::

        >>> extract_domain("https://www.netflix.com/signup")
        'netflix.com'
        >>> extract_domain("https://app.slack.com/client")
        'slack.com'
        >>> extract_domain("https://bbc.co.uk/news")
        'bbc.co.uk'
    """
    extracted = _TLD_EXTRACT(url)
    return f"{extracted.domain}.{extracted.suffix}"
