"""
No-KYC Visa Card Monitor
"""

import os
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from search_sources import search_all_sources
from enrich import enrich_result

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

CSV_HEADERS = [
    "date_found",
    "source_platform",
    "source_url",
    "card_name",
    "card_type",
    "company_name",
    "company_website",
    "app_store_link",
    "play_store_link",
    "parent_company",
    "issuing_bank",
    "ceo_or_founders",
    "contact_email",
    "physical_address",
    "phone_number",
    "terms_conditions_url",
    "privacy_policy_url",
    "notes",
]


def load_existing_urls(csv_path: Path) -> set:
    urls = set()
    if csv_path.exists():
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                urls.add(row.get("source_url", ""))
    return urls


def run():
    logger.info("=" * 60)
    logger.info("No-KYC Visa Card Monitor — Starting daily scan")
    logger.info("=" * 60)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    rolling_csv = OUTPUT_DIR / "all_results.csv"
    daily_csv = OUTPUT_DIR / f"results_{today}.csv"

    existing_urls = load_existing_urls(rolling_csv)
    logger.info(f"Loaded {len(existing_urls)} previously seen URLs")

    logger.info("Step 1: Searching all sources...")
    raw_results = search_all_sources()
    logger.info(f"Found {len(raw_results)} raw results across all sources")

    new_results = [r for r in raw_results if r.get("source_url") not in existing_urls]
    logger.info(f"{len(new_results)} new results after deduplication")

    if not new_results:
        logger.info("No new results today. Done!")
        with open(daily_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
        return

    logger.info("Step 2: Enriching results...")
    enriched = []
    for i, result in enumerate(new_results, 1):
        logger.info(f"  Enriching {i}/{len(new_results)}: {result.get('card_name', 'Unknown')}")
        try:
            enriched_result = enrich_result(result)
            enriched_result["date_found"] = today
            enriched.append(enriched_result)
        except Exception as e:
            logger.error(f"  Error enriching result: {e}")
            result["date_found"] = today
            result["notes"] = result.get("notes", "") + f" | Enrichment failed: {e}"
            enriched.append(result)

    logger.info("Step 3: Writing CSV output...")

    with open(daily_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in enriched:
            writer.writerow(row)
    logger.info(f"  Daily results written to {daily_csv}")

    file_exists = rolling_csv.exists()
    with open(rolling_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for row in enriched:
            writer.writerow(row)
    logger.info(f"  Appended to rolling file {rolling_csv}")

    json_path = LOG_DIR / f"raw_{today}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, default=str)
    logger.info(f"  Debug JSON saved to {json_path}")

    logger.info(f"Done! Found {len(enriched)} new card(s) today.")


if __name__ == "__main__":
    run()
