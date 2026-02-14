from src.models.user import UserTier

# Monthly limits per tier (analyses per month)
TIER_LIMITS = {
    UserTier.FREE: 3,  # 3 analyses per month
    UserTier.PRO: 999999,  # Effectively unlimited
    # Legacy tiers map to Pro limits
    UserTier.INDIVIDUAL: 999999,
    UserTier.BUSINESS: 999999,
    UserTier.ENTERPRISE: 999999,
}

# Tier pricing (USD per month)
TIER_PRICES = {
    UserTier.FREE: 0,
    UserTier.PRO: 9,  # $9/month
    # Legacy
    UserTier.INDIVIDUAL: 9,
    UserTier.BUSINESS: 49,
    UserTier.ENTERPRISE: 500,
}

# Tier display names
TIER_DISPLAY_NAMES = {
    UserTier.FREE: "Free",
    UserTier.PRO: "Pro",
    # Legacy
    UserTier.INDIVIDUAL: "Pro",
    UserTier.BUSINESS: "Pro",
    UserTier.ENTERPRISE: "Pro",
}

# Tier descriptions
TIER_DESCRIPTIONS = {
    UserTier.FREE: "Perfect for trying out Clausea with basic privacy analysis.",
    UserTier.PRO: "Unlimited analysis for privacy-conscious individuals and teams.",
    # Legacy
    UserTier.INDIVIDUAL: "Unlimited analysis for privacy-conscious individuals and teams.",
    UserTier.BUSINESS: "Unlimited analysis for privacy-conscious individuals and teams.",
    UserTier.ENTERPRISE: "Unlimited analysis for privacy-conscious individuals and teams.",
}
