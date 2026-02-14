from src.models.user import UserTier

# Monthly limits per tier (analyses per month)
TIER_LIMITS = {
    UserTier.FREE: 3,  # 3 analyses per month
    UserTier.INDIVIDUAL: 999999,  # Effectively unlimited (rate-limited per minute)
    UserTier.BUSINESS: 999999,  # Effectively unlimited (rate-limited per minute)
    UserTier.ENTERPRISE: 999999,  # Effectively unlimited (rate-limited per minute)
}

# Tier pricing (USD per month)
TIER_PRICES = {
    UserTier.FREE: 0,
    UserTier.INDIVIDUAL: 9,  # $9/month or $84/year ($7/mo effective)
    UserTier.BUSINESS: 49,  # $49/month or $468/year ($39/mo effective)
    UserTier.ENTERPRISE: 500,  # Custom pricing, starting at $500/month
}

# Tier display names
TIER_DISPLAY_NAMES = {
    UserTier.FREE: "Free",
    UserTier.INDIVIDUAL: "Individual",
    UserTier.BUSINESS: "Business",
    UserTier.ENTERPRISE: "Enterprise",
}

# Tier descriptions
TIER_DESCRIPTIONS = {
    UserTier.FREE: "Perfect for trying out Clausea with basic privacy analysis.",
    UserTier.INDIVIDUAL: "For privacy-conscious individuals who want unlimited analysis.",
    UserTier.BUSINESS: "For growing legal teams and small businesses.",
    UserTier.ENTERPRISE: "For large legal teams and organizations with advanced needs.",
}
