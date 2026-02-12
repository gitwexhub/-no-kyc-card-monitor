"""
Enrichment Module - Claude AI Powered
======================================
Visits company websites and uses Claude to intelligently
extract issuing bank, contacts, and leadership info.
"""

import os
import re
import json
import logging
import requests
from urllib.parse import urljoin, urlparse
from typing import Dict, Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def enrich_result(result: Dict) -> Dict:
    website = result.get("company_website", "")
    if not website or not website.startswith("http"):
        source_url = result.get("source_url", "")
        if source_url and not any(s in source_url for s in ["reddit.com", "x.com", "twitter.com"]):
            website = source_url
        else:
            result["notes"] = result.get("notes", "") + " | No website found to enrich"
            return result

    try:
        base_domain = get_base_url(website)
        logger.info(f"    Enriching from {base_domain}")

        # Collect all page texts for Claude to analyze
        pages_text = {}

        # Fetch main page
        main_html = fetch_page(base_domain)
        if not main_html:
            result["notes"] = result.get("notes", "") + " | Could not fetch website"
            return result

        pages_text["homepage"] = clean_html(main_html)

        # Find and fetch key pages
        app_store = find_app_store_link(main_html, "apple")
        play_store = find_app_store_link(main_html, "google")
        if app_store:
            result["app_store_link"] = app_store
        if play_store:
            result["play_store_link"] = play_store

        # Find Terms & Conditions
        tos_url = find_page_link(main_html, base_domain, [
            "terms-and-conditions", "terms-of-service", "terms_of_service",
            "termsandconditions", "termsofservice", "tos", "terms-of-use",
            "terms", "legal", "user-agreement", "cardholder-agreement",
            "card-agreement",
        ])
        if tos_url:
            result["terms_conditions_url"] = tos_url
            tos_html = fetch_page(tos_url)
            if tos_html:
                pages_text["terms_and_conditions"] = clean_html(tos_html)

        # Find Privacy Policy
        privacy_url = find_page_link(main_html, base_domain, [
            "privacy-policy", "privacy_policy", "privacypolicy", "privacy",
        ])
        if privacy_url:
            result["privacy_policy_url"] = privacy_url
            privacy_html = fetch_page(privacy_url)
            if privacy_html:
                pages_text
