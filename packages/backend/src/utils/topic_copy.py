"""Consumer-facing copy for topic cards on product overviews.

Each topic stance shown to users has two one-sentence strings:
``why_it_matters`` explains why the topic matters to a person deciding whether
to use a product, and ``recommended_action`` tells them what to do about it.

These tables and helpers replace the B2B-procurement fallbacks that used to
live in ``src/analyser.py``. The copy is plain English, second person, and
concrete — no "vendor", "onboarding", "deployment", or legal jargon.
"""

from __future__ import annotations

TOPIC_WHY_IT_MATTERS: dict[str, str] = {
    "data_collection": "This determines what personal information the company gathers about you, and how much of your life they can see.",
    "data_purposes": "This explains what the company is allowed to use your data for, and whether those uses go beyond what you'd expect.",
    "data_sharing": "This determines whether your data is shared with other companies, and how much exposure you have.",
    "user_rights": "This sets out what you can do with your data — see it, change it, or delete it — and how hard the company makes that.",
    "retention": "This controls how long your data is kept after you stop using the service.",
    "deletion": "This determines whether you can actually get your data removed, and whether they have to confirm it's gone.",
    "security": "This indicates how well the company protects your data from hacks, leaks, and unauthorized access.",
    "advertising": "This decides whether your data is used to target ads at you, and how much advertisers learn about you.",
    "profiling_ai": "This determines whether you're scored or profiled by automated systems, and how those profiles affect you.",
    "data_sale": "This decides whether the company can sell your data to others for profit.",
    "cookies_tracking": "This controls how much of your browsing is tracked across sites through cookies and similar tech.",
    "children": "This covers how the service handles data from children, and what protections apply if kids use it.",
    "dangers": "This highlights the privacy risks the company itself admits to, so you know what could go wrong.",
    "benefits": "This shows the privacy protections and user-friendly practices the company commits to, so you know what you're getting.",
    "recommended_actions": "This summarizes the steps the company suggests you take to protect your privacy while using the service.",
    "liability": "This limits what the company is responsible for if something goes wrong with your data or account.",
    "arbitration": "This determines whether you can take the company to court, or whether you're forced into private arbitration instead.",
    "governing_law": "This sets which country's or state's laws apply to your relationship with the company.",
    "jurisdiction": "This determines where any legal disputes would have to be filed, which can mean traveling far from home.",
    "international_transfers": "This decides whether your data is sent to other countries, and which privacy protections travel with it.",
    "government_access": "This covers whether and how the company shares your data with governments and law enforcement.",
    "corporate_family_sharing": "This determines whether your data is shared within the company's corporate group, including affiliates you may not have heard of.",
    "ai_training": "This decides whether your prompts, posts, or content can be used to train the company's AI models.",
    "automated_decisions": "This determines whether algorithms can make significant decisions about you without a human in the loop.",
    "content_ownership": "This sets who owns the content you post, and what the company can do with it.",
    "scope_expansion": "This covers whether the company can expand how it uses your data later, even if it started narrow.",
    "indemnification": "This determines whether you'd have to pay the company's legal costs if a dispute arises from your use.",
    "termination_consequences": "This explains what happens to your data and access if the company closes your account or shuts down.",
    "consent_mechanisms": 'This controls how the company asks for your agreement, and whether saying "no" is a real option.',
    "account_lifecycle": "This covers what happens to your data as you sign up, use, and eventually leave the service.",
    "breach_notification": "This determines whether and how quickly the company tells you if your data is exposed in a breach.",
    "dispute_resolution": "This sets the process for resolving problems with the company, and whether you can resolve them informally or need a lawyer.",
}

TOPIC_RECOMMENDED_ACTIONS: dict[str, str] = {
    "data_collection": "Review what you're asked to share during sign-up, and skip optional fields that aren't needed to use the service.",
    "data_purposes": "Read the listed uses and turn off any optional ones in your account settings if you can.",
    "data_sharing": "Check your privacy settings and turn off third-party data sharing if the option exists.",
    "user_rights": "Try exporting your data once now, so you know the workflow works before you need it.",
    "retention": "Delete your account when you stop using the service, and ask them to confirm data removal.",
    "deletion": "Request deletion of your data through their privacy tool or by email, and keep a copy of the request.",
    "security": "Turn on two-factor authentication and a strong password, since you can't control how they store your data.",
    "advertising": "Look for an ad-personalization opt-out in your account settings and turn it off.",
    "profiling_ai": "Look for a profiling or automated-decision opt-out in your settings, or email them to opt out.",
    "data_sale": 'Find the "do not sell my personal information" link and submit the opt-out if your region offers one.',
    "cookies_tracking": "Reject optional cookies in the cookie banner, and consider a browser extension that blocks trackers.",
    "children": "Don't let children sign up for a service that isn't clearly built for them, and review what data kids' accounts collect.",
    "dangers": "Read the risks the company lists and decide whether you're comfortable accepting them before signing up.",
    "benefits": "Take advantage of the privacy controls the company offers, and review them periodically to make sure they're still on.",
    "recommended_actions": "Follow the steps the company itself recommends, since they know their own settings best.",
    "liability": "Know the limits before you rely on the service for anything important, and keep your own backups.",
    "arbitration": "Check whether you can opt out of arbitration within the allowed window — many policies let you, but only briefly after signing up.",
    "governing_law": "Note which country or state's laws apply, in case you ever need to raise a dispute.",
    "jurisdiction": "Know where you'd have to file a dispute, and weigh that before relying on the service for anything serious.",
    "international_transfers": "Check whether your data leaves your home country, and look for a transfer opt-out if your region offers one.",
    "government_access": "Read what the company says about government requests, and consider that if it matters to you.",
    "corporate_family_sharing": "Check whether you can opt out of sharing with the company's affiliates, and turn it off if you can.",
    "ai_training": "Look for an AI-training opt-out in your account settings, or email the company to opt out.",
    "automated_decisions": "If you're affected by an automated decision, ask the company for a human review — you may have that right.",
    "content_ownership": "Read the license you grant on your posts, and avoid uploading content you don't want the company to reuse.",
    "scope_expansion": "Check periodically for policy updates, since the company may broaden how it uses your data over time.",
    "indemnification": "Know whether you'd owe them legal costs, and avoid uses that could trigger a dispute.",
    "termination_consequences": "Export your data regularly so you don't lose everything if your account is closed.",
    "consent_mechanisms": "Choose the most protective consent option available, and revisit it if the company changes how it asks.",
    "account_lifecycle": "Decide upfront what you'll do when you leave the service, and don't put data in you can't get out.",
    "breach_notification": "Make sure your contact info is current so you'd actually be notified if a breach happens.",
    "dispute_resolution": "Try to resolve problems with support first, and keep records of every exchange in case you need them later.",
}


def why_it_matters_for(topic: str, status: str, stance: str, conflict_count: int) -> str:
    """Return a consumer-facing "why it matters" sentence for a topic stance.

    ``topic`` is an :class:`InsightCategory` value, ``status`` is the coverage
    status (``found``/``missing``/``ambiguous``/``not_disclosed``), ``stance``
    is the risk stance, and ``conflict_count`` is how many policies disagree.
    """
    if status in {"missing", "not_disclosed"}:
        return "The policy doesn't mention this, so you can't be sure how the company handles it."
    if status == "ambiguous" or stance == "mixed":
        return f"The policies disagree on this ({conflict_count} conflict(s)), so assume the broader interpretation applies."
    return TOPIC_WHY_IT_MATTERS.get(
        topic,
        "This affects how the company handles your data in this area.",
    )


def recommended_action_for(topic: str, status: str, stance: str) -> str:
    """Return a consumer-facing "what to do" sentence for a topic stance.

    See :func:`why_it_matters_for` for argument meanings; ``conflict_count``
    is not needed for the action since the advice is the same regardless of how
    many policies disagree.
    """
    if status in {"missing", "not_disclosed"}:
        return "If this matters to you, email the company and ask them directly."
    if status == "ambiguous" or stance == "mixed":
        return "The policies disagree — assume the broader one applies and adjust your settings accordingly."
    return TOPIC_RECOMMENDED_ACTIONS.get(
        topic,
        "Review your account settings for controls related to this.",
    )
