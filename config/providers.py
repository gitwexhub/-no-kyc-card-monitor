"""
Provider configuration — populated from research data.

Each provider entry contains:
  - signup URL
  - signup type (web, telegram, api)
  - supported networks
  - fee structure
  - limits
  - notes on quirks/risks
"""

PROVIDERS = {
    # ── Web-based signup ──────────────────────────────────────────────

    "ezzocard": {
        "name": "Ezzocard",
        "url": "https://ezzocard.finance/",
        "signup_type": "web",
        "networks": ["visa", "mastercard"],
        "min_deposit_usd": 25,
        "denominations": [25, 50, 100, 200],
        "accepted_crypto": ["BTC", "ETH", "USDT-ERC20", "USDT-TRC20", "USDT-BEP20", "USDT-SOL", "DOGE", "LTC", "TRX", "SOL", "BNB"],
        "card_types": ["gold_mc", "gold_visa", "violet", "lime7", "lime30", "brown", "orange", "yellow", "maroon", "teal"],
        "denominations": [10, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000],
        "fees": {"markup_pct": "varies 5-30% over face value"},
        "limits": {"max_denomination": 10000},
        "bank_info": "US and Canadian banks (unnamed)",
        "operational_since": 2020,
        "risk_level": "medium",
        "notes": "Oldest established no-KYC provider. Both networks available.",
    },

    "solcard": {
        "name": "SolCard",
        "url": "https://solcard.io",
        "signup_type": "web",
        "networks": ["mastercard"],
        "min_deposit_usd": 10,
        "accepted_crypto": ["BTC", "ETH", "USDT", "SOL", "LTC"],
        "fees": {"topup_pct": 5.0, "monthly": 1.0},
        "limits": {"monthly_spend": 10000},
        "risk_level": "medium-high",
        "notes": (
            "No-KYC Mastercard only (Visa requires KYC since mid-2025). "
            "Reports of retroactive KYC freezes. $1/month maintenance."
        ),
    },

    "bingcard": {
        "name": "BingCard",
        "url": "https://bingcard.io",
        "signup_type": "web",
        "networks": ["visa", "mastercard"],
        "min_deposit_usd": 5,
        "accepted_crypto": ["BTC", "ETH", "USDT", "LTC", "XMR"],
        "fees": {"withdrawal_pct": 0.5},
        "limits": {"virtual_star_monthly": 200000},
        "bank_info": "Incorporated Canada 2022",
        "risk_level": "high",
        "notes": (
            "Virtual cards no-KYC (both networks). Physical Visa Platinum "
            "requires KYC. Flagged by security scanners. Mixed reliability."
        ),
    },

    "fotoncard": {
        "name": "FotonCard",
        "url": "https://fotoncard.com",
        "signup_type": "web",
        "networks": ["visa", "mastercard"],
        "min_deposit_usd": 100,
        "accepted_crypto": ["BTC", "ETH", "USDT", "USDC"],
        "fees": {"topup_pct": 3.5},
        "bank_info": "US, Hong Kong, Singapore banks",
        "risk_level": "medium",
        "notes": "$100 minimum deposit required to activate.",
    },

    "pstnet": {
        "name": "PSTnet",
        "url": "https://pst.net",
        "signup_type": "web",
        "networks": ["visa", "mastercard"],
        "min_deposit_usd": 25,
        "accepted_crypto": ["BTC", "ETH", "USDT", "USDC"],
        "fees": {"cashback_pct": 3.0},
        "limits": {},
        "bank_info": "US and European banks, 25+ proprietary BINs",
        "risk_level": "medium",
        "notes": (
            "Designed for ad/media buying. First card anonymous, "
            "then KYC required for additional. 3% cashback on ads."
        ),
    },

    "laso": {
        "name": "Laso Finance",
        "url": "https://www.laso.finance",
        "signup_type": "web",
        "networks": ["visa"],
        "min_deposit_usd": 10,
        "accepted_crypto": ["USDC", "USDT", "DAI"],
        "accepted_chains": ["ethereum", "solana", "stellar", "arbitrum", "base", "polygon", "optimism", "bnb"],
        "fees": {},
        "bank_info": "FinCEN MSB #31000249413002, Austin TX",
        "risk_level": "low-medium",
        "notes": "First no-KYC stablecoin cards. Chrome extension + mobile app.",
    },

    "linkpay": {
        "name": "LinkPay",
        "url": "https://linkpay.to",
        "signup_type": "web",
        "networks": ["visa", "mastercard"],
        "min_deposit_usd": 10,
        "accepted_crypto": ["BTC", "ETH", "USDT"],
        "fees": {"cashback_pct": 3.0},
        "risk_level": "medium",
        "notes": 'Both networks under "Omni" brand. 3% cashback.',
    },

    "kripicard": {
        "name": "KripiCard",
        "url": "https://kripicard.com",
        "signup_type": "web",
        "networks": ["visa"],
        "min_deposit_usd": 10,
        "accepted_crypto": ["USDT"],
        "risk_level": "medium",
        "notes": "USDT virtual cards, evidence points to Visa network.",
    },

    "paywide": {
        "name": "PayWide",
        "url": "https://paywide.io",
        "signup_type": "web",
        "networks": ["visa", "mastercard"],
        "accepted_crypto": ["BTC", "ETH", "USDT"],
        "bank_info": "Taiwan-based (Wage3/WageCan)",
        "risk_level": "medium",
        "notes": "Both networks. Taiwan-based via Wage3/WageCan.",
    },

    "xkard": {
        "name": "XKard",
        "url": "https://xkard.io",
        "signup_type": "web",
        "networks": ["visa"],
        "accepted_crypto": ["BTC", "ETH", "USDT"],
        "bank_info": "Hong Kong Visa, operates as 'Xhype'",
        "risk_level": "high",
        "notes": (
            "Zero-knowledge model advertised BUT users report funds frozen "
            "for 'mixer activity in transaction chain' with forced KYC."
        ),
    },

    "plasbit": {
        "name": "PlasBit",
        "url": "https://plasbit.com",
        "signup_type": "web",
        "networks": ["visa", "mastercard"],
        "accepted_crypto": ["BTC", "ETH", "USDT", "USDC"],
        "bank_info": "Registered in Poland",
        "risk_level": "medium",
        "notes": "Both networks. User reports indicate prepaid cards often Mastercard.",
    },

    "zypto": {
        "name": "Zypto",
        "url": "https://zypto.com",
        "signup_type": "web",
        "networks": ["mastercard"],
        "accepted_crypto": ["BTC", "ETH", "USDT", "100+ cryptos"],
        "risk_level": "low-medium",
        "notes": (
            "Soft-KYC Mastercard (no document uploads). "
            "Visa Premium requires full KYC. ZYP rewards points."
        ),
    },

    "rewarble": {
        "name": "Rewarble",
        "url": "https://rewarble.com",
        "signup_type": "web",
        "networks": ["mastercard"],
        "accepted_crypto": ["BTC", "ETH", "USDT"],
        "risk_level": "low",
        "notes": "Virtual prepaid Mastercard gift cards.",
    },

    # ── Telegram-based signup ─────────────────────────────────────────

    "zeroid_cc": {
        "name": "ZeroID CC",
        "url": "https://t.me/ZeroID_bot",  # UPDATE with actual bot
        "signup_type": "telegram",
        "networks": ["visa", "mastercard"],
        "accepted_crypto": ["BTC", "LTC", "USDT"],
        "risk_level": "high",
        "notes": "Both networks via Telegram bot. Possibly Zypto reseller.",
    },

    # ── Aggregator / Reseller ─────────────────────────────────────────

    "trocador": {
        "name": "Trocador",
        "url": "https://trocador.app",
        "signup_type": "web",
        "networks": ["visa", "mastercard"],
        "accepted_crypto": ["BTC", "XMR", "LTC", "ETH"],
        "fees": {"fx_pct": 2.0},
        "risk_level": "medium",
        "notes": (
            "Aggregator model. Mastercard intl up to $1K, Visa US up to $10K. "
            "EUR card supply issues."
        ),
    },

    # ── Not yet operational / Not cards ───────────────────────────────

    "offgrid_cash": {
        "name": "OffGrid Cash",
        "url": "https://offgridcash.com",
        "signup_type": "web",
        "networks": ["visa"],
        "risk_level": "unknown",
        "notes": "WAITLIST ONLY — not yet operational. Visa planned.",
        "operational": False,
    },

    "0fiat": {
        "name": "0Fiat",
        "url": "https://0fiat.com",
        "signup_type": "none",
        "networks": [],
        "risk_level": "low",
        "notes": (
            "NOT A CARD — browser extension for direct wallet-to-merchant "
            "crypto payments. 80+ stores, no KYC, zero fees."
        ),
        "is_card": False,
    },
}


# Pre-filter to only operational card providers
ACTIVE_CARD_PROVIDERS = {
    k: v for k, v in PROVIDERS.items()
    if v.get("operational", True) and v.get("is_card", True)
}


def get_provider(name: str) -> dict:
    """Get a provider config by name."""
    return PROVIDERS.get(name, {})


def list_by_network(network: str) -> list[str]:
    """List provider names that support a given card network."""
    network = network.lower()
    return [
        k for k, v in ACTIVE_CARD_PROVIDERS.items()
        if network in v.get("networks", [])
    ]


def list_by_crypto(crypto: str) -> list[str]:
    """List providers that accept a specific cryptocurrency."""
    crypto = crypto.upper()
    return [
        k for k, v in ACTIVE_CARD_PROVIDERS.items()
        if crypto in v.get("accepted_crypto", [])
    ]
