from src.models.user import UserTier

# Monthly limits per tier (analyses per month)
TIER_LIMITS = {
    UserTier.FREE: 3,  # 3 analyses per month
    UserTier.PRO: 999999,  # Effectively unlimited
}

# Tier pricing (USD)
TIER_PRICES = {
    UserTier.FREE: 0,
    UserTier.PRO: 9,  # $9/month
}

TIER_PRICES_ANNUAL = {
    UserTier.FREE: 0,
    UserTier.PRO: 100,  # $100/year
}

# Tier display names
TIER_DISPLAY_NAMES = {
    UserTier.FREE: "Free",
    UserTier.PRO: "Pro",
}

# Tier descriptions
TIER_DESCRIPTIONS = {
    UserTier.FREE: "Perfect for trying out Clausea with basic privacy analysis.",
    UserTier.PRO: "Unlimited analysis for privacy-conscious individuals and teams.",
}
