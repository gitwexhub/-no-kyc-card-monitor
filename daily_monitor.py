#!/usr/bin/env python3
"""
Daily No-KYC Card Monitor

Runs daily to:
1. Scan all known providers for card availability and prices
2. Search for new no-KYC card providers
3. Output results to JSON and optionally notify via Telegram

Usage:
    python daily_monitor.py [--telegram] [--output results.json]
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright

from config.providers import ACTIVE_CARD_PROVIDERS
from agents.ezzocard_agent import EzzocardAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("daily_monitor")

# Output directory
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


async def monitor_ezzocard() -> dict:
    """Monitor Ezzocard for available cards."""
    agent = EzzocardAgent(config={
        "monitor_only": True,
        "headless": True,
        "denomination": 50,
        "card_type": "violet",
        "crypto": "btc",
    })

    try:
        result = await agent.signup()
        return {
            "provider": "ezzocard",
            "status": result.status.value if result.status else "unknown",
            "network": result.network.value if result.network else "unknown",
            "catalog": result.metadata.get("catalog", []),
            "total_products": result.metadata.get("total_products", 0),
            "in_stock": result.metadata.get("in_stock_count", 0),
            "target_found": result.metadata.get("target_found", False),
            "target_price": result.metadata.get("target_price"),
            "error": result.error,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Ezzocard monitoring failed: {e}")
        return {
            "provider": "ezzocard",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


async def monitor_generic_provider(browser, provider_name: str, provider_info: dict) -> dict:
    """
    Generic provider monitor - just checks if site is accessible.
    TODO: Build specific agents for each provider.
    """
    result = {
        "provider": provider_name,
        "name": provider_info.get("name"),
        "url": provider_info.get("url"),
        "networks": provider_info.get("networks", []),
        "status": "unchecked",
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        url = provider_info.get("url", "")
        if not url or url.startswith("https://t.me"):
            result["status"] = "skipped"
            result["note"] = "Telegram-based or no URL"
            await context.close()
            return result

        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        page_text = (await page.text_content("body") or "").lower()

        # Basic checks
        result["accessible"] = True
        result["has_card_mentions"] = any(w in page_text for w in ["visa", "mastercard", "card", "prepaid"])
        result["has_crypto_mentions"] = any(w in page_text for w in ["btc", "bitcoin", "usdt", "crypto", "eth"])
        result["has_pricing"] = "$" in page_text or "usd" in page_text

        # Check for common issues
        if "coming soon" in page_text or "waitlist" in page_text:
            result["status"] = "not_operational"
        elif "maintenance" in page_text or "temporarily" in page_text:
            result["status"] = "maintenance"
        elif result["has_card_mentions"] and result["has_crypto_mentions"]:
            result["status"] = "operational"
        else:
            result["status"] = "unclear"

        await context.close()
        logger.info(f"{provider_name}: {result['status']}")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["accessible"] = False
        logger.warning(f"{provider_name}: {e}")

    return result


async def search_new_providers(browser) -> list:
    """
    Search the web for new no-KYC card providers.
    Uses DuckDuckGo to find potential new providers.
    """
    logger.info("Searching for new no-KYC card providers...")

    search_queries = [
        "no KYC crypto card 2024 2025",
        "anonymous prepaid card cryptocurrency",
        "buy visa card with bitcoin no verification",
        "no kyc virtual card crypto",
        "anonymous mastercard bitcoin",
    ]

    new_finds = []
    known_domains = set()

    # Extract known domains
    for p in ACTIVE_CARD_PROVIDERS.values():
        url = p.get("url", "")
        if url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "")
                known_domains.add(domain)
            except:
                pass

    try:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        for query in search_queries[:2]:  # Limit to avoid rate limiting
            try:
                search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
                await page.goto(search_url, timeout=30000)
                await page.wait_for_timeout(3000)

                # Extract links from search results
                links = await page.locator("a[href*='http']").all()

                for link in links[:20]:
                    try:
                        href = await link.get_attribute("href")
                        text = await link.text_content() or ""

                        if not href or "duckduckgo" in href:
                            continue

                        from urllib.parse import urlparse
                        domain = urlparse(href).netloc.replace("www.", "")

                        # Skip known providers and common sites
                        skip_domains = ["reddit.com", "twitter.com", "youtube.com", "medium.com",
                                       "github.com", "t.me", "telegram", "facebook.com"]

                        if domain in known_domains:
                            continue
                        if any(s in domain for s in skip_domains):
                            continue

                        # Check if it looks like a card provider
                        text_lower = text.lower()
                        if any(w in text_lower for w in ["card", "visa", "mastercard", "prepaid", "crypto"]):
                            new_finds.append({
                                "url": href,
                                "domain": domain,
                                "title": text[:100],
                                "found_via": query,
                            })
                            known_domains.add(domain)  # Avoid duplicates

                    except:
                        continue

            except Exception as e:
                logger.warning(f"Search query failed: {e}")
                continue

        await context.close()

    except Exception as e:
        logger.error(f"New provider search failed: {e}")

    # Deduplicate by domain
    seen = set()
    unique_finds = []
    for f in new_finds:
        if f["domain"] not in seen:
            seen.add(f["domain"])
            unique_finds.append(f)

    logger.info(f"Found {len(unique_finds)} potential new providers")
    return unique_finds


async def send_telegram_notification(results: dict, bot_token: str, chat_id: str):
    """Send monitoring results via Telegram."""
    import httpx

    # Build message
    msg_parts = ["🔍 *Daily No-KYC Card Monitor*\n"]
    msg_parts.append(f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")

    # Provider summary
    operational = sum(1 for r in results.get("providers", []) if r.get("status") == "operational")
    total = len(results.get("providers", []))
    msg_parts.append(f"\n*Providers:* {operational}/{total} operational\n")

    # Ezzocard details
    for p in results.get("providers", []):
        if p["provider"] == "ezzocard" and p.get("in_stock"):
            msg_parts.append(f"\n*Ezzocard:* {p['in_stock']} cards in stock")
            if p.get("target_price"):
                msg_parts.append(f" (target: ${p['target_price']})")

    # New providers
    new_providers = results.get("new_providers", [])
    if new_providers:
        msg_parts.append(f"\n\n*{len(new_providers)} Potential New Providers:*")
        for np in new_providers[:5]:
            msg_parts.append(f"\n• {np['domain']}")

    message = "".join(msg_parts)

    # Send via Telegram API
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        })


async def main():
    """Main monitoring routine."""
    import argparse

    parser = argparse.ArgumentParser(description="Daily No-KYC Card Monitor")
    parser.add_argument("--telegram", action="store_true", help="Send results via Telegram")
    parser.add_argument("--output", type=str, help="Output JSON file path")
    parser.add_argument("--search-new", action="store_true", default=True, help="Search for new providers")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Starting Daily No-KYC Card Monitor")
    logger.info("=" * 60)

    results = {
        "run_date": datetime.utcnow().isoformat(),
        "providers": [],
        "new_providers": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 1. Monitor Ezzocard (full agent - manages own browser)
        logger.info("\n--- Monitoring Ezzocard ---")
        ezzocard_result = await monitor_ezzocard()
        results["providers"].append(ezzocard_result)

        # 2. Check other providers (basic accessibility)
        logger.info("\n--- Checking Other Providers ---")
        for name, info in ACTIVE_CARD_PROVIDERS.items():
            if name == "ezzocard":
                continue
            result = await monitor_generic_provider(browser, name, info)
            results["providers"].append(result)
            await asyncio.sleep(2)  # Rate limiting

        # 3. Search for new providers
        if args.search_new:
            logger.info("\n--- Searching for New Providers ---")
            results["new_providers"] = await search_new_providers(browser)

        await browser.close()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    operational = [p for p in results["providers"] if p.get("status") == "operational"]
    logger.info(f"Providers checked: {len(results['providers'])}")
    logger.info(f"Operational: {len(operational)}")
    logger.info(f"New providers found: {len(results['new_providers'])}")

    # Save results
    output_file = args.output or OUTPUT_DIR / f"monitor_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Results saved to: {output_file}")

    # Also save latest.json for easy access
    latest_file = OUTPUT_DIR / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Send Telegram notification if requested
    if args.telegram:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if bot_token and chat_id:
            await send_telegram_notification(results, bot_token, chat_id)
            logger.info("Telegram notification sent")
        else:
            logger.warning("Telegram credentials not set (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")

    return results


if __name__ == "__main__":
    asyncio.run(main())
