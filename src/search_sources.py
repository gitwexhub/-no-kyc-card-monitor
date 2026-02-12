"""
Search Sources Module - SerpAPI Version
========================================
Focused on finding actual companies selling no-KYC Visa cards.
"""

import os
import re
import time
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    # Find actual product pages
    '"no KYC" Visa card sign up',
    '"no KYC" Visa debit card order',
    '"no KYC" Visa prepaid card buy',
    '"no KYC" virtual Visa card',
    '"KYC free" Visa card',
    '"without KYC" Visa card',
    '"no verification" Visa card crypto',
    'anonymous Visa debit card buy',
    'no identity verification Visa card',

    # Crypto-specific (most no-KYC cards are crypto-funded)
    'crypto debit card no KYC Visa',
    'bitcoin Visa card no KYC',
    'USDT Visa card no verification',
    'stablecoin Visa card anonymous',
    'crypto to Visa card no ID',

    # App store searches
    'site:apps.apple.com no KYC Visa card',
    'site:play.google.com no KYC Visa card',

    # Find company websites directly
    '"issued by" "no KYC" Visa card',
    '"terms and conditions" "no KYC" Visa card',
    '"get your card" "no KYC" Visa',
    '"order card" "no KYC" Visa',
    '"sign up" "no verification" Visa card',
]


def search_all_sources() -> List[Dict]:
    results = []

    serpapi_key = os.environ.get("SERPAPI_KEY")
    if not serpapi_key:
        logger.error("SERPAPI_KEY is required. Cannot search.")
        return results

    logger.info(f"  Running {len(SEARCH_QUERIES)} search queries via SerpAPI...")

    for i, query in enumerate(SEARCH_QUERIES, 1):
        logger.info(f"  Query {i}/{len(SEARCH_QUERIES)}: {query}")
        try:
            query_results = serpapi_search(query, serpapi_key)
            results.extend(query_results)
            logger.info(f"    Found {len(query_results)} results")
        except Exception as e:
            logger.error(f"    Error: {e}")
        time.sleep(2)

    seen = set()
    unique = []
    for r in results:
        url = normalize_url(r.get("source_url", ""))
        if url and url not in seen:
            seen.add(url)
            unique.append(r)

    logger.info(f"  Total unique results: {len(unique)}")
    return unique


def serpapi_search(query: str, api_key: str) -> List[Dict]:
    results = []

    url = "https://serpapi.com/search"
    params = {
        "api_key": api_key,
        "engine": "google",
        "q": query,
        "num": 10,
    }

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    for item in data.get("organic_results", []):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        displayed_link = item.get("displayed_link", "")
        combined_text = f"{title} {snippet}"

        source_platform = detect_platform(link, displayed_link)

        if not is_relevant(combined_text):
            continue

        # Skip pure discussion/article sites - we want company sites
        if is_discussion_only(link, combined_text):
            continue

        company_website = extract_company_website(link, snippet, source_platform)

        results.append({
            "source_platform": source_platform,
            "source_url": link,
            "card_name": extract_card_name(title, snippet),
            "card_type": detect_card_type(combined_text),
            "company_name": extract_company_from_snippet(title, snippet),
            "company_website": company_website if company_website else link,
            "notes": snippet[:500],
        })

    return results


def normalize_url(url: str) -> str:
    url = url.rstrip("/")
    url = re.sub(r'^https?://(www\.)?', '', url)
    return url.lower()


def detect_platform(url: str, display_link: str) -> str:
    url_lower = url.lower()
    if "reddit.com" in url_lower:
        match = re.search(r'reddit\.com/r/([^/]+)', url_lower)
        if match:
            return f"Reddit r/{match.group(1)}"
        return "Reddit"
    elif "x.com" in url_lower or "twitter.com" in url_lower:
        return "X/Twitter"
    elif "medium.com" in url_lower:
        return "Medium"
    elif "linkedin.com" in url_lower:
        return "LinkedIn"
    elif "bitcointalk.org" in url_lower:
        return "BitcoinTalk"
    elif "trustpilot.com" in url_lower:
        return "Trustpilot"
    elif "producthunt.com" in url_lower:
        return "Product Hunt"
    elif "youtube.com" in url_lower:
        return "YouTube"
    elif "apps.apple.com" in url_lower:
        return "App Store"
    elif "play.google.com" in url_lower:
        return "Google Play"
    else:
        return f"Web ({display_link})"


def is_relevant(text: str) -> bool:
    text_lower = text.lower()
    has_visa = "visa" in text_lower
    has_no_kyc = any(phrase in text_lower for phrase in [
        "no kyc", "no-kyc", "nokyc", "no know your customer",
        "without kyc", "kyc-free", "kyc free", "no verification",
        "no id required", "anonymous card", "no identity",
        "anonymous", "no id verification",
    ])
    has_card = any(word in text_lower for word in [
        "card", "prepaid", "debit", "credit", "virtual card",
    ])
    return has_visa and (has_no_kyc or has_card)


def is_discussion_only(url: str, text: str) -> bool:
    """Filter out pure news/discussion that aren't actual card providers."""
    url_lower = url.lower()
    skip_domains = [
        "wikipedia.org", "investopedia.com", "nerdwallet.com",
        "forbes.com", "cointelegraph.com", "coindesk.com",
        "techcrunch.com", "theverge.com",
    ]
    for domain in skip_domains:
        if domain in url_lower:
            return True
    return False


def detect_card_type(text: str) -> str:
    text_lower = text.lower()
    types = []
    if "prepaid" in text_lower:
        types.append("Prepaid")
    if "debit" in text_lower:
        types.append("Debit")
    if "credit" in text_lower:
        types.append("Credit")
    if "virtual" in text_lower:
        types.append("Virtual")
    return "/".join(types) if types else "Unknown"


def extract_card_name(title: str, body: str) -> str:
    combined = f"{title} {body}"
    patterns = [
        r'([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\s+(?:Visa|Card|card)',
        r'(?:Visa|card|Card)\s+(?:by|from)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)',
        r'([A-Z][A-Za-z0-9]{2,})\s+(?:prepaid|debit|credit|virtual)',
    ]
    for patter
