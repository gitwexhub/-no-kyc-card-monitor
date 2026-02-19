"""
Enrichment Module - Claude AI Powered
"""

import os
import re
import json
import logging
import requests
from urllib.parse import urljoin, urlparse

from search_sources import fetch_app_store_metadata, fetch_play_store_metadata

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def enrich_result(result):
    website = result.get("company_website", "")
    platform = result.get("source_platform", "")
    source_url = result.get("source_url", "")
    app_metadata = None

    # For App Store/Google Play results, fetch metadata for fallback info
    if platform in ("App Store", "Google Play"):
        logger.info("    Fetching app store metadata for %s", source_url)
        if platform == "App Store":
            app_metadata = fetch_app_store_metadata(source_url)
        elif platform == "Google Play":
            app_metadata = fetch_play_store_metadata(source_url)

        if app_metadata:
            # Use metadata for website if not already set
            if app_metadata.get("developer_website") and (not website or not website.startswith("http")):
                website = app_metadata["developer_website"]
                result["company_website"] = website
            # Store metadata for fallback use later
            if app_metadata.get("developer_name"):
                result["_fallback_company"] = app_metadata["developer_name"]
            if app_metadata.get("app_name"):
                result["_fallback_card"] = app_metadata["app_name"]

    if not website or not website.startswith("http"):
        # Don't use forum/social URLs as company website
        skip_sources = ["reddit.com", "x.com", "twitter.com", "bitcointalk.org", "medium.com"]
        if source_url and not any(skip in source_url.lower() for skip in skip_sources):
            website = source_url
        else:
            # Use fallback data if available
            if result.get("_fallback_company"):
                result["company_name"] = result.pop("_fallback_company")
            if result.get("_fallback_card"):
                result["card_name"] = result.pop("_fallback_card")
            result["notes"] = result.get("notes", "") + " | No website found"
            return result

    # Helper function to derive names from domain
    def derive_names_from_url(url):
        """Extract company name from domain, excluding common platform domains."""
        skip_domains = ["apps.apple.com", "play.google.com", "reddit.com", "x.com",
                        "twitter.com", "bitcointalk.org", "medium.com"]
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "").lower()
        for skip in skip_domains:
            if skip in domain:
                return None
        domain_parts = domain.split(".")
        if domain_parts:
            return domain_parts[0].title()
        return None
    try:
        base_domain = get_base_url(website)
        logger.info("    Enriching from %s", base_domain)
        pages_text = {}
        main_html = fetch_page(base_domain)
        if not main_html:
            # Website fetch failed - use fallback or derive from domain
            if result.get("_fallback_company"):
                result["company_name"] = result.pop("_fallback_company")
            elif not result.get("company_name"):
                derived = derive_names_from_url(base_domain)
                if derived:
                    result["company_name"] = derived

            if result.get("_fallback_card"):
                result["card_name"] = result.pop("_fallback_card")
            elif not result.get("card_name"):
                if result.get("company_name"):
                    result["card_name"] = result["company_name"] + " Card"
                else:
                    # Derive from domain directly
                    derived = derive_names_from_url(base_domain)
                    if derived:
                        result["card_name"] = derived + " Card"

            result.pop("_fallback_company", None)
            result.pop("_fallback_card", None)
            result["notes"] = result.get("notes", "") + " | Could not fetch website"
            return result
        pages_text["homepage"] = clean_html(main_html)
        app_store = find_app_store_link(main_html, "apple")
        play_store = find_app_store_link(main_html, "google")
        if app_store:
            result["app_store_link"] = app_store
        if play_store:
            result["play_store_link"] = play_store
        tos_url = find_page_link(main_html, base_domain, [
            "terms-and-conditions", "terms-of-service", "termsofservice",
            "tos", "terms-of-use", "terms", "legal",
            "user-agreement", "cardholder-agreement", "card-agreement",
        ])
        if tos_url:
            result["terms_conditions_url"] = tos_url
            tos_html = fetch_page(tos_url)
            if tos_html:
                pages_text["terms_and_conditions"] = clean_html(tos_html)
        privacy_url = find_page_link(main_html, base_domain, [
            "privacy-policy", "privacy_policy", "privacypolicy", "privacy",
        ])
        if privacy_url:
            result["privacy_policy_url"] = privacy_url
            privacy_html = fetch_page(privacy_url)
            if privacy_html:
                pages_text["privacy_policy"] = clean_html(privacy_html)
        about_url = find_page_link(main_html, base_domain, [
            "about-us", "about", "our-team", "team",
            "leadership", "company", "who-we-are",
        ])
        if about_url:
            about_html = fetch_page(about_url)
            if about_html:
                pages_text["about_page"] = clean_html(about_html)
        contact_url = find_page_link(main_html, base_domain, [
            "contact-us", "contact", "support", "get-in-touch", "help",
        ])
        if contact_url:
            contact_html = fetch_page(contact_url)
            if contact_html:
                pages_text["contact_page"] = clean_html(contact_html)
        if os.environ.get("ANTHROPIC_API_KEY"):
            claude_data = analyze_with_claude(pages_text, base_domain)
            if claude_data:
                for key, val in claude_data.items():
                    if val and val.lower() not in ("unknown", "not found", "n/a", "none", ""):
                        result[key] = val

        # Use fallback values if Claude didn't extract card_name or company_name
        if not result.get("company_name") and result.get("_fallback_company"):
            result["company_name"] = result["_fallback_company"]
        if not result.get("card_name") and result.get("_fallback_card"):
            result["card_name"] = result["_fallback_card"]

        # Last resort: derive company name from domain (but not for platform domains)
        if not result.get("company_name"):
            derived = derive_names_from_url(base_domain)
            if derived:
                result["company_name"] = derived

        # Last resort: derive card name from company name or domain
        if not result.get("card_name"):
            if result.get("company_name"):
                result["card_name"] = result["company_name"] + " Card"
            else:
                # Derive from domain directly
                derived = derive_names_from_url(base_domain)
                if derived:
                    result["card_name"] = derived + " Card"

        result["company_website"] = base_domain

        # Clean up fallback fields
        result.pop("_fallback_company", None)
        result.pop("_fallback_card", None)

    except Exception as e:
        logger.error("    Enrichment error: %s", e)
        result["notes"] = result.get("notes", "") + " | Enrichment error: " + str(e)
    return result


def analyze_with_claude(pages_text, website):
    api_key = os.environ["ANTHROPIC_API_KEY"]
    max_chars = 15000
    combined_text = ""
    for page_name, text in pages_text.items():
        combined_text += "\n\n=== " + page_name.upper() + " ===\n" + text[:max_chars]
    combined_text = combined_text[:60000]
    prompt = """Analyze the following website content from """ + website + """ and extract information about this company that offers a Visa card product.

CRITICAL - You MUST extract these two fields accurately:
1. "company_name": The official name of the company/startup/fintech that operates this website and offers the card product. Look for:
   - Company name in header/logo area
   - "About Us" section
   - Footer copyright (e.g., "© 2024 CompanyName")
   - Legal/Terms pages

2. "card_name": The specific name of their Visa card product. Look for:
   - Product branding (e.g., "Coinbase Card", "BitPay Card", "Revolut Card")
   - Marketing headlines about the card
   - If no specific product name, use format: "[CompanyName] Card"

IMPORTANT for "issuing_bank": This is the LICENSED BANK that actually issues the Visa card, NOT the app/fintech company.
- Look for phrases like: "issued by", "cards are issued by", "pursuant to a license from Visa", "Member FDIC", "banking services provided by"
- Common issuing banks: Metropolitan Commercial Bank, Sutton Bank, Evolve Bank & Trust, Cross River Bank, Celtic Bank, Pathward, Stride Bank, Choice Financial Group, The Bancorp
- The issuing bank is typically mentioned in Terms & Conditions, footer disclosures, or cardholder agreements
- Do NOT confuse the app company with the issuing bank

Return ONLY valid JSON with these fields:
{
    "company_name": "Official company name (REQUIRED - extract from website)",
    "card_name": "Name of their Visa card product (REQUIRED - extract from website)",
    "card_type": "Prepaid, Debit, Credit, and/or Virtual",
    "parent_company": "Parent or holding company if mentioned",
    "issuing_bank": "The licensed bank that issues the card (NOT the app company)",
    "ceo_or_founders": "Names and titles like Name (Title); Name (Title)",
    "contact_email": "Contact email addresses",
    "physical_address": "Physical or mailing address",
    "phone_number": "Phone number"
}

Use empty string "" for fields not found. Return ONLY valid JSON, no other text.

WEBSITE CONTENT:
""" + combined_text
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        response_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                response_text += block["text"]
        response_text = response_text.strip()
        response_text = re.sub(r'^```json\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)
        parsed = json.loads(response_text)
        logger.info("    Claude found: bank=%s, company=%s", parsed.get("issuing_bank", "?"), parsed.get("company_name", "?"))
        return parsed
    except json.JSONDecodeError as e:
        logger.error("    Claude returned invalid JSON: %s", e)
        return None
    except Exception as e:
        logger.error("    Claude API error: %s", e)
        return None


def fetch_page(url, timeout=15):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug("    Could not fetch %s: %s", url, e)
        return None


def get_base_url(url):
    parsed = urlparse(url)
    return parsed.scheme + "://" + parsed.netloc


def clean_html(html):
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def find_page_link(html, base_url, keywords):
    link_pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    for match in re.finditer(link_pattern, html, re.IGNORECASE | re.DOTALL):
        href = match.group(1)
        link_text = re.sub(r'<[^>]+>', '', match.group(2)).lower()
        href_lower = href.lower()
        for keyword in keywords:
            if keyword in href_lower or keyword.replace("-", " ") in link_text:
                full_url = urljoin(base_url, href)
                if full_url.startswith("http"):
                    return full_url
    return None


def find_app_store_link(html, store):
    if store == "apple":
        pattern = r'https?://(?:apps\.apple\.com|itunes\.apple\.com)/[^\s"\'<>]+'
    else:
        pattern = r'https?://play\.google\.com/store/apps/[^\s"\'<>]+'
    match = re.search(pattern, html)
    return match.group(0) if match else ""
