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
from agents.bin_lookup import BINLookup
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
        if card.bin_number:
            print(f"     BIN:     {card.bin_number} ({card.network.value})")
        if card.card_number_last4:
            print(f"     Last 4:  {card.card_number_last4}")
        if card.expiry:
            print(f"     Expiry:  {card.expiry}")
        if card.error:
            print(f"     Error:   {card.error}")
        if card.deposit_address:
            print(f"     Deposit: {card.deposit_address[:20]}...")

    # Write JSON output file (with BIN lookups)
    await _write_output_file(results)


async def _write_output_file(results: list):
    """Write results to output/cards_YYYYMMDD.json with BIN lookup data."""
    from pathlib import Path

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"cards_{ts}.json"

    # Run BIN lookups for all cards that have BINs
    bin_lookup = BINLookup()
    bins_to_lookup = [c.bin_number for c in results if c.bin_number]
    bin_results = {}

    if bins_to_lookup:
        logger.info(f"Looking up {len(bins_to_lookup)} BIN(s)...")
        for bin_num in bins_to_lookup:
            info = await bin_lookup.lookup(bin_num)
            bin_results[bin_num] = info
            logger.info(f"  BIN {bin_num}: {info.summary}")

    output_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_attempted": len(results),
        "total_issued": sum(1 for c in results if c.status == SignupStatus.CARD_ISSUED),
        "total_awaiting": sum(1 for c in results if c.status == SignupStatus.AWAITING_DEPOSIT),
        "total_failed": sum(1 for c in results if c.status == SignupStatus.FAILED),
        "bins_collected": [],
        "cards": [],
    }

    for card in results:
        bin_info = bin_results.get(card.bin_number)

        card_entry = {
            "provider": card.provider,
            "status": card.status.value,
            "network": card.network.value,
            "bin_number": card.bin_number,
            "card_number_last4": card.card_number_last4,
            "expiry": card.expiry,
            "denomination": card.metadata.get("denomination_usd"),
            "card_type": card.metadata.get("card_color"),
            "created_at": card.created_at,
        }

        # Add BIN lookup data if available
        if bin_info and bin_info.issuer_bank:
            card_entry["issuer_bank"] = bin_info.issuer_bank
            card_entry["issuer_country"] = bin_info.country_code
            card_entry["card_scheme"] = bin_info.scheme
            card_entry["card_category"] = bin_info.category
            card_entry["is_prepaid"] = bin_info.is_prepaid
            card_entry["bin_lookup_source"] = bin_info.source

        output_data["cards"].append(card_entry)

        # Collect BINs with full lookup context
        if card.bin_number:
            bin_entry = {
                "bin": card.bin_number,
                "provider": card.provider,
                "network": card.network.value,
                "card_type": card.metadata.get("card_color", "unknown"),
                "denomination": card.metadata.get("denomination_usd"),
            }
            if bin_info and bin_info.issuer_bank:
                bin_entry.update({
                    "issuer_bank": bin_info.issuer_bank,
                    "issuer_country": bin_info.country_code,
                    "issuer_url": bin_info.issuer_url,
                    "card_scheme": bin_info.scheme,
                    "card_category": bin_info.category,
                    "is_prepaid": bin_info.is_prepaid,
                    "currency": bin_info.currency,
                    "lookup_source": bin_info.source,
                })
            output_data["bins_collected"].append(bin_entry)

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info(f"Output written to {output_path}")
    print(f"\nOutput file: {output_path}")

    # Also print a BIN summary table if any were collected
    if output_data["bins_collected"]:
        print(f"\n{'='*60}")
        print("BIN NUMBERS COLLECTED")
        print(f"{'='*60}")
        print(f"  {'BIN':<12} {'Network':<10} {'Issuer Bank':<30} {'Country':<6} {'Provider'}")
        print(f"  {'-'*76}")
        for b in output_data["bins_collected"]:
            bank = b.get('issuer_bank', '?')
            country = b.get('issuer_country', '?')
            print(
                f"  {b['bin']:<12} {b['network']:<10} {bank:<30} "
                f"{country:<6} {b['provider']}"
            )


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

    print(f"\n{'Provider':<20} {'Status':<18} {'Network':<12} {'BIN':<12} {'Last4':<8} {'Card ID':<14} {'Created'}")
    print("-" * 100)
    for card in cards:
        print(
            f"{card.provider:<20} {card.status.value:<18} "
            f"{card.network.value:<12} {(card.bin_number or '-'):<12} "
            f"{(card.card_number_last4 or '-'):<8} {card.card_id[:12]:<14} "
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
