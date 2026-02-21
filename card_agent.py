#!/usr/bin/env python3
"""
no-kyc-card-agent — Orchestrator for automated card signups.

Usage:
    # Sign up for a single provider
    python -m card_agent signup ezzocard

    # Sign up for all active providers
    python -m card_agent signup --all

    # Health check all issued cards
    python -m card_agent health-check

    # List stored cards
    python -m card_agent list

    # List available providers
    python -m card_agent providers
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from agents import AgentRegistry
from agents.base_agent import CardResult, SignupStatus
from config.providers import ACTIVE_CARD_PROVIDERS, PROVIDERS
from storage import CardStore
from crypto import PaymentManager

# ── Logging setup ─────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/agent_{datetime.now().strftime('%Y%m%d')}.log"),
    ],
)
logger = logging.getLogger("orchestrator")


# ── Load config ───────────────────────────────────────────────────────

def load_config(path: str = "config/agent_config.json") -> dict:
    """Load agent configuration (proxies, keys, etc.)."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Config file {path} not found, using defaults")
        return {}


# ── Commands ──────────────────────────────────────────────────────────

async def cmd_signup(args, config: dict):
    """Sign up for one or more card providers."""
    registry = AgentRegistry()
    registry.discover()
    store = CardStore(password=config.get("store_password", ""))

    providers = (
        list(ACTIVE_CARD_PROVIDERS.keys()) if args.all
        else [args.provider]
    )

    # Optional: set up payment manager for auto-deposits
    payment_mgr = None
    if config.get("auto_deposit") and config.get("crypto"):
        payment_mgr = PaymentManager(config["crypto"])

    results = []
    for provider_name in providers:
        if provider_name not in ACTIVE_CARD_PROVIDERS:
            logger.warning(f"Skipping unknown/inactive provider: {provider_name}")
            continue

        provider_conf = ACTIVE_CARD_PROVIDERS[provider_name]
        agent_config = {
            **config.get("global_agent", {}),
            **config.get(f"agent_{provider_name}", {}),
        }

        agent = registry.get(provider_name, config=agent_config)
        if not agent:
            logger.warning(
                f"No agent implementation for '{provider_name}' — "
                f"signup type: {provider_conf.get('signup_type')}"
            )
            continue

        logger.info(f"{'='*60}")
        logger.info(f"Starting signup for: {provider_name}")
        logger.info(f"{'='*60}")

        card = await agent.signup()
        results.append(card)

        # Store result regardless of outcome
        store.save(card)

        # Auto-deposit if configured and card is awaiting deposit
        if (
            payment_mgr
            and card.status == SignupStatus.AWAITING_DEPOSIT
            and card.deposit_address
            and card.deposit_amount
        ):
            logger.info(
                f"Auto-depositing {card.deposit_amount} {card.deposit_currency} "
                f"to {card.deposit_address[:16]}..."
            )
            payment = await payment_mgr.send_deposit(
                to_address=card.deposit_address,
                amount=card.deposit_amount,
                currency=card.deposit_currency or "USDT",
                chain=card.deposit_chain,
            )
            if payment.success:
                card.status = SignupStatus.DEPOSIT_SENT
                card.metadata["deposit_tx"] = payment.tx_hash
                store.save(card)
                logger.info(f"Deposit sent! TX: {payment.tx_hash}")
            else:
                logger.error(f"Deposit failed: {payment.error}")

        # Brief pause between providers
        if len(providers) > 1:
            await asyncio.sleep(5)

    # Summary
    print(f"\n{'='*60}")
    print("SIGNUP SUMMARY")
    print(f"{'='*60}")
    for card in results:
        status_icon = {
            SignupStatus.CARD_ISSUED: "✅",
            SignupStatus.AWAITING_DEPOSIT: "💰",
            SignupStatus.DEPOSIT_SENT: "📤",
            SignupStatus.FAILED: "❌",
            SignupStatus.FROZEN: "🧊",
        }.get(card.status, "⏳")

        print(f"  {status_icon} {card.provider:20s} → {card.status.value}")
        if card.error:
            print(f"     Error: {card.error}")
        if card.deposit_address:
            print(f"     Deposit: {card.deposit_address[:20]}...")


async def cmd_health_check(args, config: dict):
    """Run health checks on all issued cards."""
    registry = AgentRegistry()
    registry.discover()
    store = CardStore(password=config.get("store_password", ""))

    cards = store.list_active()
    if not cards:
        print("No active cards to check.")
        return

    print(f"Checking {len(cards)} active card(s)...\n")

    for card in cards:
        agent_config = config.get(f"agent_{card.provider}", {})
        agent = registry.get(card.provider, config=agent_config)

        if not agent:
            print(f"  ⚠️  {card.provider:20s} — no agent, skipping")
            continue

        healthy = await agent.health_check(card)
        icon = "✅" if healthy else "🧊"
        print(f"  {icon} {card.provider:20s} card={card.card_id[:8]}... → {'ACTIVE' if healthy else 'FROZEN'}")

        if not healthy:
            store.save(card)  # Save the updated frozen status


async def cmd_list(args, config: dict):
    """List all stored cards."""
    store = CardStore(password=config.get("store_password", ""))
    cards = store.list_all()

    if not cards:
        print("No cards stored.")
        return

    print(f"\n{'Provider':<20} {'Status':<18} {'Network':<12} {'Card ID':<14} {'Created'}")
    print("-" * 80)
    for card in cards:
        print(
            f"{card.provider:<20} {card.status.value:<18} "
            f"{card.network.value:<12} {card.card_id[:12]:<14} "
            f"{card.created_at[:10]}"
        )


def cmd_providers(args, config: dict):
    """List all configured providers."""
    print(f"\n{'Provider':<20} {'Type':<12} {'Networks':<20} {'Risk':<12} {'Status'}")
    print("-" * 80)

    for name, p in sorted(PROVIDERS.items()):
        operational = p.get("operational", True) and p.get("is_card", True)
        status = "✅ Active" if operational else "⏸️  Inactive"
        networks = ", ".join(p.get("networks", []))
        print(
            f"{name:<20} {p.get('signup_type', '?'):<12} "
            f"{networks:<20} {p.get('risk_level', '?'):<12} {status}"
        )


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="No-KYC Card Signup Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", default="config/agent_config.json",
        help="Path to config JSON",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # signup
    p_signup = sub.add_parser("signup", help="Sign up for card(s)")
    p_signup.add_argument("provider", nargs="?", help="Provider name")
    p_signup.add_argument("--all", action="store_true", help="All providers")

    # health-check
    sub.add_parser("health-check", help="Check active cards")

    # list
    sub.add_parser("list", help="List stored cards")

    # providers
    sub.add_parser("providers", help="List available providers")

    args = parser.parse_args()
    config = load_config(args.config)

    if args.command == "signup":
        if not args.provider and not args.all:
            parser.error("Specify a provider name or --all")
        asyncio.run(cmd_signup(args, config))
    elif args.command == "health-check":
        asyncio.run(cmd_health_check(args, config))
    elif args.command == "list":
        asyncio.run(cmd_list(args, config))
    elif args.command == "providers":
        cmd_providers(args, config)


if __name__ == "__main__":
    main()
