"""
Enrichment Module - Claude AI Powered
"""

import os
import re
import json
import logging
import requests
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def enrich_result(result):
    website = result.get("company_website", "")
    if not website or not website.startswith("http"):
        source_url = result.get("source_url", "")
        if source_url and "reddit.com" not in source_url and "x.com" not in source_url:
            website = source_url
        else:
            result["notes"] = result.get("notes", "") + " | No website found"
            return result
    try:
        base_domain = get_base_url(website)
        logger.info("    Enriching from %s", base_domain)
        pages_text = {}
        main_html = fetch_page(base_domain)
        if not main_html:
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
        result["company_website"] = base_domain
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

Return ONLY valid JSON with these fields:
{
    "company_name": "Official company name",
    "parent_company": "Parent or holding company if mentioned",
    "issuing_bank": "Bank that issues the Visa card - look for phrases like issued by, issuing bank, pursuant to a license from Visa, member FDIC",
    "ceo_or_founders": "Names and titles like Name (Title); Name (Title)",
    "contact_email": "Contact email addresses",
    "physical_address": "Physical or mailing address",
    "phone_number": "Phone number",
    "card_name": "Name of their Visa card product",
    "card_type": "Prepaid, Debit, Credit, and/or Virtual"
}

Use empty string "" for fields not found. Return ONLY JSON.

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
