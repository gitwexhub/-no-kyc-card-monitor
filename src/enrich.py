"""
Enrichment Module
=================
Visits company websites to find issuing bank, contacts, leadership info.
"""

import os
import re
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

TOS_KEYWORDS = [
    "terms-and-conditions", "terms-of-service", "terms_of_service",
    "termsandconditions", "termsofservice", "tos", "terms-of-use",
    "terms", "legal", "user-agreement",
]

PRIVACY_KEYWORDS = [
    "privacy-policy", "privacy_policy", "privacypolicy", "privacy",
]

ISSUING_BANK_PATTERNS = [
    r"(?:issued|issuing|issuer|issuance)\s+(?:by|bank|institution|partner)[:\s]+([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\n|<)",
    r"(?:bank|banking)\s+(?:partner|provider|institution)[:\s]+([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\n|<)",
    r"cards?\s+(?:are|is)\s+issued\s+by\s+([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\n|<)",
    r"(?:licensed|regulated|authorized)\s+by\s+([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\n|<)",
    r"member\s+(?:FDIC|fdic)[\s.,;]+([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\n|<)",
    r"pursuant\s+to\s+(?:a\s+)?license\s+from\s+Visa[^.]*by\s+([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\n|<)",
]

EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_PATTERN = r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
ADDRESS_PATTERN = r'\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Suite|Ste|Floor|Fl)[.,\s]+[A-Za-z\s]+,\s*[A-Z]{2}\s+\d{5}'


def enrich_result(result: Dict) -> Dict:
    website = result.get("company_website", "")
    if not website or not website.startswith("http"):
        source_url = result.get("source_url", "")
        if source_url and "reddit.com" not in source_url and "x.com" not in source_url:
            website = source_url
        else:
            result["notes"] = result.get("notes", "") + " | No website found to enrich"
            return result

    try:
        base_domain = get_base_url(website)
        logger.info(f"    Enriching from {base_domain}")

        main_html = fetch_page(base_domain)
        if not main_html:
            result["notes"] = result.get("notes", "") + " | Could not fetch website"
            return result

        result["company_name"] = result.get("company_name") or extract_company_name(main_html, base_domain)

        result["app_store_link"] = find_app_store_link(main_html, "apple")
        result["play_store_link"] = find_app_store_link(main_html, "google")

        tos_url = find_legal_page(main_html, base_domain, TOS_KEYWORDS)
        if tos_url:
            result["terms_conditions_url"] = tos_url
            tos_html = fetch_page(tos_url)
            if tos_html:
                bank = extract_issuing_bank(tos_html)
                if bank:
                    result["issuing_bank"] = bank
                parent = extract_parent_company(tos_html)
                if parent:
                    result["parent_company"] = parent

        privacy_url = find_legal_page(main_html, base_domain, PRIVACY_KEYWORDS)
        if privacy_url:
            result["privacy_policy_url"] = privacy_url
            privacy_html = fetch_page(privacy_url)
            if privacy_html:
                if not result.get("issuing_bank"):
                    bank = extract_issuing_bank(privacy_html)
                    if bank:
                        result["issuing_bank"] = bank
                contacts = extract_contacts(privacy_html)
                result.update(contacts)

        about_url = find_about_page(main_html, base_domain)
        if about_url:
            about_html = fetch_page(about_url)
            if about_html:
                people = extract_leadership(about_html)
                if people:
                    result["ceo_or_founders"] = people

        contact_url = find_contact_page(main_html, base_domain)
        if contact_url:
            contact_html = fetch_page(contact_url)
            if contact_html:
                contacts = extract_contacts(contact_html)
                for key, val in contacts.items():
                    if val and not result.get(key):
                        result[key] = val

        main_contacts = extract_contacts(main_html)
        for key, val in main_contacts.items():
            if val and not result.get(key):
                result[key] = val

        if not result.get("parent_company"):
            parent = extract_copyright_owner(main_html)
            if parent:
                result["parent_company"] = parent

    except Exception as e:
        logger.error(f"    Enrichment error: {e}")
        result["notes"] = result.get("notes", "") + f" | Enrichment error: {e}"

    return result


def fetch_page(url: str, timeout: int = 15) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug(f"    Could not fetch {url}: {e}")
        return None


def get_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def find_legal_page(html: str, base_url: str, keywords: list) -> Optional[str]:
    link_pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    for match in re.finditer(link_pattern, html, re.IGNORECASE | re.DOTALL):
        href = match.group(1)
        link_text = match.group(2).lower()
        href_lower = href.lower()
        for keyword in keywords:
            if keyword in href_lower or keyword.replace("-", " ") in link_text:
                return urljoin(base_url, href)
    return None


def find_about_page(html: str, base_url: str) -> Optional[str]:
    about_keywords = ["about-us", "about", "our-team", "team", "leadership", "company"]
    return find_legal_page(html, base_url, about_keywords)


def find_contact_page(html: str, base_url: str) -> Optional[str]:
    contact_keywords = ["contact-us", "contact", "support", "get-in-touch"]
    return find_legal_page(html, base_url, contact_keywords)


def find_app_store_link(html: str, store: str) -> str:
    if store == "apple":
        pattern = r'https?://(?:apps\.apple\.com|itunes\.apple\.com)/[^\s"\'<>]+'
    else:
        pattern = r'https?://play\.google\.com/store/apps/[^\s"\'<>]+'
    match = re.search(pattern, html)
    return match.group(0) if match else ""


def extract_company_name(html: str, base_url: str) -> str:
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()
        for sep in ["|", "-", "–", "—", ":"]:
            if sep in title:
                return title.split(sep)[0].strip()
        return title[:100]
    parsed = urlparse(base_url)
    return parsed.netloc.replace("www.", "")


def extract_issuing_bank(html: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    for pattern in ISSUING_BANK_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            bank = match.group(1).strip()
            bank = re.sub(r'[,.]$', '', bank).strip()
            if len(bank) > 5 and len(bank) < 100:
                return bank
    return ""


def extract_parent_company(html: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    patterns = [
        r'(?:subsidiary|affiliate|owned by|operated by|a product of|a service of|part of)\s+([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\n)',
        r'([A-Z][A-Za-z\s&.,]+?)\s+(?:and its subsidiaries|and affiliates|group|holdings)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            parent = match.group(1).strip()
            parent = re.sub(r'[,.]$', '', parent).strip()
            if len(parent) > 3 and len(parent) < 100:
                return parent
    return ""


def extract_copyright_owner(html: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', html)
    match = re.search(r'©\s*(?:\d{4}\s*)?([A-Z][A-Za-z\s&.,]+?)(?:\.|All rights|<|\n)', text)
    if match:
        return match.group(1).strip().rstrip(",. ")
    return ""


def extract_leadership(html: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    titles = [
        "CEO", "Chief Executive Officer",
        "Founder", "Co-Founder", "Co-founder",
        "CTO", "Chief Technology Officer",
        "President", "Managing Director",
    ]
    people = []
    for title in titles:
        patterns = [
            rf'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[,\-–]\s*{title}',
            rf'{title}\s*[,\-–:]\s*([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip()
