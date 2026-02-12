"""
Search Sources Module - SerpAPI Version
"""

import os
import re
import time
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    '"no KYC" Visa card sign up',
    '"no KYC" Visa debit card order',
    '"no KYC" Visa prepaid card buy',
    '"no KYC" virtual Visa card',
    '"KYC free" Visa card',
    '"without KYC" Visa card',
    '"no verification" Visa card crypto',
    'anonymous Visa debit card buy',
    'no identity verification Visa card',
    'crypto debit card no KYC Visa',
    'bitcoin Visa card no KYC',
    'USDT Visa card no verification',
    'stablecoin Visa card anonymous',
    'crypto to Visa card no ID',
    'site:apps.apple.com no KYC Visa card',
    'site:play.google.com no KYC Visa card',
    '"issued by" "no KYC" Visa card',
    '"terms and conditions" "no KYC" Visa card',
    '"get your card" "no KYC" Visa',
    '"order card" "no KYC" Visa',
    '"sign up" "no verification" Visa card',
]


def search_all_sources():
    results = []
    serpapi_key = os.environ.get("SERPAPI_KEY")
    if not serpapi_key:
        logger.error("SERPAPI_KEY is required. Cannot search.")
        return results

    logger.info("  Running %d search queries via SerpAPI...", len(SEARCH_QUERIES))

    for i, query in enumerate(SEARCH_QUERIES, 1):
        logger.info("  Query %d/%d: %s", i, len(SEARCH_QUERIES), query)
        try:
            query_results = serpapi_search(query, serpapi_key)
            results.extend(query_results)
            logger.info("    Found %d results", len(query_results))
        except Exception as e:
            logger.error("    Error: %s", e)
        time.sleep(2)

    seen = set()
    unique = []
    for r in results:
        url = normalize_url(r.get("source_url", ""))
        if url and url not in seen:
            seen.add(url)
            unique.append(r)

    logger.info("  Total unique results: %d", len(unique))
    return unique


def serpapi_search(query, api_key):
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
        combined_text = title + " " + snippet

        source_platform = detect_platform(link, displayed_link)

        if not is_relevant(combined_text):
            continue

        if is_discussion_only(link):
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


def normalize_url(url):
    url = url.rstrip("/")
    url = re.sub(r'^https?://(www\.)?', '', url)
    return url.lower()


def detect_platform(url, display_link):
    u = url.lower()
    if "reddit.com" in u:
        match = re.search(r'reddit\.com/r/([^/]+)', u)
        if match:
            return "Reddit r/" + match.group(1)
        return "Reddit"
    elif "x.com" in u or "twitter.com" in u:
        return "X/Twitter"
    elif "medium.com" in u:
        return "Medium"
    elif "linkedin.com" in u:
        return "LinkedIn"
    elif "bitcointalk.org" in u:
        return "BitcoinTalk"
    elif "trustpilot.com" in u:
        return "Trustpilot"
    elif "producthunt.com" in u:
        return "Product Hunt"
    elif "youtube.com" in u:
        return "YouTube"
    elif "apps.apple.com" in u:
        return "App Store"
    elif "play.google.com" in u:
        return "Google Play"
    else:
        return "Web (" + display_link + ")"


def is_relevant(text):
    t = text.lower()
    has_visa = "visa" in t
    has_no_kyc = False
    kyc_phrases = [
        "no kyc", "no-kyc", "nokyc", "no know your customer",
        "without kyc", "kyc-free", "kyc free", "no verification",
        "no id required", "anonymous card", "no identity",
        "anonymous", "no id verification",
    ]
    for phrase in kyc_phrases:
        if phrase in t:
            has_no_kyc = True
            break
    has_card = False
    card_words = ["card", "prepaid", "debit", "credit", "virtual card"]
    for word in card_words:
        if word in t:
            has_card = True
            break
    return has_visa and (has_no_kyc or has_card)


def is_discussion_only(url):
    u = url.lower()
    skip = [
        "wikipedia.org", "investopedia.com", "nerdwallet.com",
        "forbes.com", "cointelegraph.com", "coindesk.com",
        "techcrunch.com", "theverge.com",
    ]
    for domain in skip:
        if domain in u:
            return True
    return False


def detect_card_type(text):
    t = text.lower()
    types = []
    if "prepaid" in t:
        types.append("Prepaid")
    if "debit" in t:
        types.append("Debit")
    if "credit" in t:
        types.append("Credit")
    if "virtual" in t:
        types.append("Virtual")
    return "/".join(types) if types else "Unknown"


def extract_card_name(title, body):
    combined = title + " " + body
    patterns = [
        r'([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\s+(?:Visa|Card|card)',
        r'(?:Visa|card|Card)\s+(?:by|from)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)',
        r'([A-Z][A-Za-z0-9]{2,})\s+(?:prepaid|debit|credit|virtual)',
    ]
    skip_words = [
        "the", "a", "an", "this", "my", "your", "no", "new",
        "best", "top", "get", "buy", "free", "any", "our",
    ]
    for pattern in patterns:
        match = re.search(pattern, combined)
        if match:
            name = match.group(1).strip()
            if name.lower() not in skip_words:
                return name
    clean_title = re.split(r'\s*[-|:\u2013\u2014]', title)[0].strip()
    return clean_title[:100] if clean_title else "Unknown"


def extract_company_from_snippet(title, snippet):
    combined = title + " " + snippet
    pattern = r'(?:by|from|offered by|powered by|issued by)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)'
    match = re.search(pattern, combined)
    if match:
        return match.group(1).strip()
    return ""


def extract_company_website(source_url, snippet, platform):
    if platform.startswith(("Reddit", "X/Twitter", "Medium", "BitcoinTalk", "LinkedIn")):
        url_pattern = r'https?://[^\s<>"\'\]).,]+'
        urls = re.findall(url_pattern, snippet)
        skip = ["reddit.com", "twitter.com", "x.com", "medium.com",
                "linkedin.com", "bitcointalk.org", "t.co"]
        for url in urls:
            u = url.lower()
            if not any(s in u for s in skip):
                return url
        return ""
    if platform.startswith(("Web", "App Store", "Google Play")):
        from urllib.parse import urlparse
        parsed = urlparse(source_url)
        return parsed.scheme + "://" + parsed.netloc
    return source_url
