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

        # Extract website URL (this is reliable)
        company_website = extract_company_website(link, snippet, source_platform)

        # For App Store/Google Play, fetch metadata to get developer website
        if source_platform == "App Store":
            metadata = fetch_app_store_metadata(link)
            if metadata and metadata.get("developer_website"):
                company_website = metadata["developer_website"]
        elif source_platform == "Google Play":
            metadata = fetch_play_store_metadata(link)
            if metadata and metadata.get("developer_website"):
                company_website = metadata["developer_website"]

        # card_name and company_name will be extracted by Claude during enrichment
        # from the actual website content (much more accurate than parsing snippets)
        results.append({
            "source_platform": source_platform,
            "source_url": link,
            "card_name": "",  # Will be populated by Claude enrichment
            "card_type": detect_card_type(combined_text),
            "company_name": "",  # Will be populated by Claude enrichment
            "company_website": company_website if company_website else "",
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

    # Patterns to extract card names, including camelCase app names
    patterns = [
        # CamelCase app names like BitPay, CashApp, Revolut
        r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b',
        r'([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\s+(?:Visa|Card|card)',
        r'(?:Visa|card|Card)\s+(?:by|from)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)',
        r'([A-Z][A-Za-z0-9]{2,})\s+(?:prepaid|debit|credit|virtual)',
    ]

    # Expanded skip words including generic terms
    skip_words = {
        "the", "a", "an", "this", "my", "your", "no", "new",
        "best", "top", "get", "buy", "free", "any", "our", "how", "can", "i",
        # Generic card/payment terms to skip
        "visa", "mastercard", "debit", "credit", "prepaid", "virtual",
        "card", "cards", "payment", "payments", "service", "services",
        # Marketing/KYC adjectives
        "cheapest", "anonymous", "crypto", "bitcoin", "kyc", "verification",
        "instant", "fast", "easy", "simple", "secure", "safe", "low", "fee",
        # Other generic terms
        "app", "apps", "download", "store", "play", "google", "apple",
        # Question words (for Reddit titles)
        "what", "where", "when", "why", "which", "who",
    }

    def is_valid_name(name):
        """Check if name contains at least one non-skip word."""
        words = name.lower().split()
        non_skip_words = [w for w in words if w not in skip_words]
        return len(non_skip_words) > 0

    def clean_name(name):
        """Remove skip words from name, keeping only meaningful parts."""
        words = name.split()
        cleaned = [w for w in words if w.lower() not in skip_words]
        return " ".join(cleaned)

    for pattern in patterns:
        matches = re.finditer(pattern, combined)
        for match in matches:
            name = match.group(1).strip()
            if len(name) > 2 and is_valid_name(name):
                cleaned = clean_name(name)
                if cleaned and len(cleaned) > 2:
                    return cleaned

    # Fallback: use cleaned title but filter marketing words
    clean_title = re.split(r'\s*[-|:\u2013\u2014]', title)[0].strip()

    # Comprehensive list of words to remove from fallback title
    filter_words = [
        "cheapest", "best", "top", "anonymous", "free", "new", "ultimate",
        "no kyc", "no-kyc", "nokyc", "without kyc", "kyc-free", "kyc free",
        "no verification", "no id", "anonymous",
        "visa", "mastercard", "debit", "credit", "prepaid", "virtual",
        "card", "cards",
    ]
    for word in filter_words:
        clean_title = re.sub(r'\b' + re.escape(word) + r'\b', '', clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()

    # If after cleaning we only have generic words left, return Unknown
    if not clean_title or clean_title.lower() in ["visa", "card", "debit", "credit", ""]:
        return "Unknown"

    return clean_title[:100]


def extract_company_from_snippet(title, snippet):
    combined = title + " " + snippet

    # Skip list for platform companies that shouldn't be returned as the company
    skip_companies = [
        "google llc", "google", "apple inc", "apple", "amazon",
        "microsoft", "meta", "facebook",
        # Card networks (not companies)
        "visa", "mastercard", "amex", "american express",
    ]

    # Patterns to find company names
    patterns = [
        r'(?:by|from|offered by|powered by|issued by|developed by|created by)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)',
        # Company suffixes like "Something Inc" or "Company LLC"
        r'\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\s+(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|Company|GmbH|AG|PLC)',
    ]

    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            company = match.group(1).strip()
            # Skip platform companies
            if company.lower() not in skip_companies:
                return company

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
    # For App Store/Google Play, return empty to force metadata fetch
    if platform in ("App Store", "Google Play"):
        return ""
    if platform.startswith("Web"):
        from urllib.parse import urlparse
        parsed = urlparse(source_url)
        return parsed.scheme + "://" + parsed.netloc
    return source_url


def fetch_app_store_metadata(url):
    """Fetch Apple App Store page and extract app name, developer, and developer website."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        result = {"app_name": "", "developer_name": "", "developer_website": ""}

        # Extract app name from title tag
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            # Format: "AppName on the App Store" or "AppName - App Store"
            app_name = re.sub(r'\s*[-–—]\s*(App Store|Apple).*$', '', title, flags=re.IGNORECASE)
            app_name = re.sub(r'\s+on the App Store.*$', '', app_name, flags=re.IGNORECASE)
            result["app_name"] = app_name.strip()

        # Extract developer name - look for "by" or developer link
        dev_patterns = [
            r'<a[^>]+href="[^"]*developer[^"]*"[^>]*>([^<]+)</a>',
            r'"sellerName"\s*:\s*"([^"]+)"',
            r'By\s+<a[^>]*>([^<]+)</a>',
            r'class="[^"]*developer[^"]*"[^>]*>([^<]+)<',
        ]
        for pattern in dev_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                result["developer_name"] = match.group(1).strip()
                break

        # Extract developer website - look for "Website" or "Developer Website" link
        website_patterns = [
            r'<a[^>]+href="([^"]+)"[^>]*>\s*(?:Developer\s+)?Website\s*</a>',
            r'"supportUrl"\s*:\s*"([^"]+)"',
            r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*website[^"]*"',
        ]
        for pattern in website_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                website = match.group(1)
                # Skip Apple domains
                if "apple.com" not in website.lower():
                    result["developer_website"] = website
                    break

        logger.debug("App Store metadata: %s", result)
        return result
    except Exception as e:
        logger.debug("Could not fetch App Store metadata from %s: %s", url, e)
        return None


def fetch_play_store_metadata(url):
    """Fetch Google Play Store page and extract app name, developer, and developer website."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        result = {"app_name": "", "developer_name": "", "developer_website": ""}

        # Extract app name from title
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            # Format: "AppName - Apps on Google Play"
            app_name = re.sub(r'\s*[-–—]\s*Apps on Google Play.*$', '', title, flags=re.IGNORECASE)
            result["app_name"] = app_name.strip()

        # Extract developer name
        dev_patterns = [
            r'<a[^>]+href="/store/apps/developer[^"]*"[^>]*>([^<]+)</a>',
            r'itemprop="author"[^>]*>.*?itemprop="name"[^>]*>([^<]+)<',
            r'"developer"[^}]*"name"\s*:\s*"([^"]+)"',
            r'<span[^>]*>Offered by</span>\s*<span[^>]*>([^<]+)</span>',
        ]
        for pattern in dev_patterns:
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if match:
                dev_name = match.group(1).strip()
                # Skip Google LLC
                if dev_name.lower() != "google llc":
                    result["developer_name"] = dev_name
                    break

        # Extract developer website - "Visit website" link
        website_patterns = [
            r'<a[^>]+href="([^"]+)"[^>]*>Visit\s+website</a>',
            r'"developerWebsite"\s*:\s*"([^"]+)"',
            r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*dev-link[^"]*"',
        ]
        for pattern in website_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                website = match.group(1)
                # Skip Google/Play Store domains
                if "google.com" not in website.lower() and "play.google.com" not in website.lower():
                    result["developer_website"] = website
                    break

        logger.debug("Play Store metadata: %s", result)
        return result
    except Exception as e:
        logger.debug("Could not fetch Play Store metadata from %s: %s", url, e)
        return None
