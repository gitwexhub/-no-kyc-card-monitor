#!/usr/bin/env python3
"""
Dry-run test — validates the Ezzocard agent against the live site
WITHOUT sending any crypto. Stops at the deposit address step.

Usage:
    pip install playwright cryptography
    playwright install chromium
    python test_dry_run.py

What it does:
    1. Launches a browser (visible, not headless)
    2. Goes to ezzocard.finance
    3. Finds a $50 Violet Visa card
    4. Adds to cart, selects BTC payment
    5. Clicks BUY NOW
    6. Extracts the deposit address
    7. Takes screenshots at every step
    8. Prints results — does NOT send any crypto

Check logs/screenshots/ after running to see what happened.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.ezzocard_agent import EzzocardAgent
from agents.base_agent import SignupStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


async def main():
    print("=" * 60)
    print("EZZOCARD DRY RUN TEST")
    print("=" * 60)
    print()
    print("This will open a browser and walk through the Ezzocard")
    print("purchase flow. NO crypto will be sent.")
    print()

    # Configure for a cheap test card
    config = {
        "headless": False,      # Set True for CI / headless servers
        "denomination": 50,     # Cheapest commonly available
        "card_type": "violet",  # Violet Visa - good availability
        "crypto": "btc",        # BTC is always available
        # "email": "test@example.com",  # Optional
        # "proxy": "socks5://...",       # Optional
    }

    agent = EzzocardAgent(config=config)
    print(f"Agent: {agent}")
    print(f"Target: ${config['denomination']} {config['card_type']}")
    print(f"Crypto: {config['crypto']}")
    print()

    # Run the signup flow
    card = await agent.signup()

    # Results
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Status:     {card.status.value}")
    print(f"  Network:    {card.network.value}")
    print(f"  Provider:   {card.provider}")

    if card.bin_number:
        print(f"  BIN (8):    {card.bin_number}")
    if card.card_number_last4:
        print(f"  Last 4:     {card.card_number_last4}")
    if card.expiry:
        print(f"  Expiry:     {card.expiry}")

    if card.deposit_address:
        print(f"  Address:    {card.deposit_address[:20]}...{card.deposit_address[-8:]}")
        print(f"  Amount:     {card.deposit_amount} {card.deposit_currency}")
        print(f"  Chain:      {card.deposit_chain}")

    if card.metadata:
        print(f"  Card type:  {card.metadata.get('card_color')} {card.metadata.get('card_network')}")
        print(f"  Price:      ${card.metadata.get('price_usd')}")

    if card.error:
        print(f"  ERROR:      {card.error}")

    print()
    print(f"Screenshots saved to: {agent.SCREENSHOT_DIR.absolute()}")

    # Check screenshots
    screenshots = list(agent.SCREENSHOT_DIR.glob("ezzocard_*.png"))
    if screenshots:
        print(f"  {len(screenshots)} screenshots captured:")
        for s in sorted(screenshots):
            print(f"    - {s.name}")

    # Test the card number extraction utility
    print()
    print("=" * 60)
    print("BIN EXTRACTION SELF-TEST")
    print("=" * 60)
    from agents.base_agent import BaseCardAgent
    test_cases = [
        ("Card: 4111 1111 1111 1111 Exp: 12/26 CVV2: 123", "41111111", "1111", "12/26", "123"),
        ("5500 0000 0000 0004 expires 03/2028 CVC: 456", "55000000", "0004", "03/2028", "456"),
        ("Your card number is 4234567890123456", "42345678", "3456", None, None),
        ("No card here, just text", None, None, None, None),
    ]
    all_pass = True
    for text, exp_bin, exp_last4, exp_expiry, exp_cvv in test_cases:
        result = BaseCardAgent._extract_card_details(text)
        ok = result["bin"] == exp_bin and result["last4"] == exp_last4
        icon = "✅" if ok else "❌"
        print(f"  {icon} BIN={result['bin']}, Last4={result['last4']}, "
              f"Exp={result['expiry']}, CVV={result['cvv']}")
        if not ok:
            print(f"     Expected: BIN={exp_bin}, Last4={exp_last4}")
            all_pass = False

    if all_pass:
        print("  All extraction tests passed!")

    # Test BIN lookup
    print()
    print("=" * 60)
    print("BIN LOOKUP DEMO")
    print("=" * 60)
    from agents.bin_lookup import BINLookup
    lookup = BINLookup()

    # Test with known BINs from the hardcoded table
    demo_bins = ["42376800", "51680500", "46000700"]
    print("  Testing known BINs (local table, no network):")
    for test_bin in demo_bins:
        info = await lookup.lookup(test_bin)
        if info.issuer_bank:
            print(f"  ✅ {info.summary}")
        else:
            print(f"  ⚠️  {test_bin}: {info.error or 'no data'}")

    # If we got a real BIN from the signup, look it up
    if card.bin_number:
        print(f"\n  Looking up actual card BIN: {card.bin_number}")
        info = await lookup.lookup(card.bin_number)
        if info.issuer_bank:
            print(f"  ✅ {info.summary}")
            print(f"     Bank:     {info.issuer_bank}")
            print(f"     Country:  {info.country or info.country_code}")
            print(f"     Type:     {info.card_type}")
            print(f"     Prepaid:  {info.is_prepaid}")
            print(f"     Source:   {info.source}")
        else:
            print(f"  ⚠️  No issuer data found ({info.error})")
            print(f"     This BIN may be new — add it manually with:")
            print(f"     lookup.add_known_bin('{card.bin_number[:6]}', 'BANK NAME')")

    print()
    if card.status == SignupStatus.AWAITING_DEPOSIT:
        print("SUCCESS! The agent reached the payment page.")
        print("In production, after sending crypto, call:")
        print("  card = await agent.wait_for_card_delivery(page, card)")
        print("to capture the BIN and full card details.")
        print()
        print("DO NOT send crypto manually — this was just a test.")
    elif card.status == SignupStatus.FAILED:
        print("FAILED — check screenshots and error above.")
        print("Common issues:")
        print("  - Card out of stock (try different denomination/type)")
        print("  - Site structure changed (selectors need updating)")
        print("  - Anti-bot detection (try adding a proxy)")
    else:
        print(f"Unexpected status: {card.status.value}")

    return card


if __name__ == "__main__":
    asyncio.run(main())
