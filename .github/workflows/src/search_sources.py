"""
Search Sources Module
=====================
Searches for Visa cards marketed as "no KYC" using Google Custom Search API.
"""

import os
import re
import time
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    'Visa card "no KYC"',
    'Visa prepaid card "no KYC"',
    'Visa debit card "no KYC"',
    'Visa credit card "no KYC"',
    '"no KYC" Visa card 2026',
    '"no kyc" Visa virtual card',
    'Visa card "without KYC"',
    'Visa card "no identity verification"',
    'Visa card "no ID required"',
    'anonymous Visa prepaid card',
    '"kyc free" Visa card',
    'crypto Visa card "no KYC"',
    'bitcoin Visa card no KYC',
    'USDT Visa card no verification',
    'site:reddit.com Visa "no KYC" card',
    'site:reddit.com anonymous Visa prepaid',
    'site:medium.com "no KYC" Visa card',
    'site:bitcointalk.org "no KYC" Visa',
    'site:linkedin.com "no KYC" Visa card',
    'site:trustpilot.com "no KYC" Visa',
    'site:producthunt.com "no KYC" Visa card',
]


def search_all_sources() -> List[Dict]:
    results = []

    if not os.environ.get("GOOGLE_API_KEY") or not os.environ.get("GOOGLE_CSE_ID"):
        logger.error("GOOGLE_API_KEY and GOOGLE_CSE_ID are required. Cannot search.")
        return results

    logger.info(f"  Running {len(SEARCH_QUERIES)} search queries via Google...")

    for i, query in enumerate(SEARCH_QUERIES, 1):
        logger.info(f"  Query {i}/{len(SEARCH_QUERIES)}: {query}")
        try:
            query_results = google_search(query)
            results.extend(query_results)
            logger.info(f"    Found {len(query_results)} results")
        except Exception as e:
            logger.error(f"    Error: {e}")

        time.sleep(1.5)

    seen = set()
    unique = []
    for r in results:
        url = r.get("source_url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)

    logger.info(f"  Total unique results: {len(unique)}")
    return unique


def google_search(query: str) -> List[Dict]:
    api_key = os.environ["GOOGLE_API_KEY"]
    cse_id = os.environ["GOOGLE_CSE_ID"]
    results = []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "num": 10,
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    for item in data.get("items", []):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        display_link = item.get("displayLink", "")
        combined_text = f"{title} {snippet}"

        source_platform = detect_platform(link, display_link)

        if not is_relevant(combined_text):
            continue

        company_website = extract_company_website(link, snippet, source_platform)

        results.append({
            "source_platform": source_platform,
            "source_url": link,
            "card_name": extract_card_name(title, snippet),
            "card_type": detect_card_type(combined_text),
            "company_name": extract_company_from_snippet(title, snippet),
            "company_website": company_website,
            "notes": snippet[:500],
        })

    return results


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
        "no id", "anonymous",
    ])
    has_card = any(word in text_lower for word in [
        "card", "prepaid", "debit", "credit", "virtual card",
    ])
    return has_visa and (has_no_kyc or has_card)


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
    for pattern in patterns:
        match = re.search(pattern, combined)
        if match:
            name = match.group(1).strip()
            if name.lower() not in (
                "the", "a", "an", "this", "my", "your", "no", "new",
                "best", "top", "get", "buy", "free", "any",
            ):
                return name
    clean_title = re.sub(r'\s*[-|:–—].*$', '', title).strip()
    return clean_title[:100] if clean_title else "Unknown"


def extract_company_from_snippet(title: str, snippet: str) -> str:
    combined = f"{title} {snippet}"
    patterns = [
        r'(?:by|from|offered by|powered by|issued by)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)',
    ]
    for pattern in patterns:
        match = re.search(pattern, combined)
        if match:
            return match.group(1).strip()
    return ""


def extract_company_website(source_url: str, snippet: str, platform: str) -> str:
    if platform.startswith(("Reddit", "X/Twitter", "Medium", "BitcoinTalk", "LinkedIn")):
        url_pattern = r'https?://[^\s<>"\'\]).,]+'
        urls = re.findall(url_pattern, snippet)
        for url in urls:
            if not any(s in url.lower() for s in [
                "reddit.com", "twitter.com", "x.com", "medium.com",
                "linkedin.com", "bitcointalk.org", "t.co",
            ]):
                return url
        return ""
    if platform.startswith("Web"):
        from urllib.parse import urlparse
        parsed = urlparse(source_url)
        return f"{parsed.scheme}://{parsed.netloc}"
    return source_url
