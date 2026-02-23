"""
BIN Lookup — resolves first 6-8 digits of a card number to issuing bank,
card type, country, and other metadata.

Uses multiple free APIs as fallbacks:
  1. binlist.net — no API key, 5 req/hr + burst of 5
  2. freebinchecker.com — no API key, generous limits
  3. Fallback: local BIN range table for common no-KYC card issuers

All results are cached in memory to avoid redundant lookups.

Usage:
    lookup = BINLookup()
    info = await lookup.lookup("45399812")
    print(info)
    # {'bin': '45399812', 'scheme': 'visa', 'type': 'prepaid',
    #  'bank': 'SUTTON BANK', 'country': 'US', ...}
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger("bin_lookup")


@dataclass
class BINInfo:
    """Result of a BIN lookup."""
    bin: str
    scheme: Optional[str] = None         # visa, mastercard
    card_type: Optional[str] = None      # debit, credit, prepaid
    category: Optional[str] = None       # classic, platinum, business, etc.
    is_prepaid: Optional[bool] = None
    issuer_bank: Optional[str] = None
    issuer_url: Optional[str] = None
    issuer_phone: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    currency: Optional[str] = None
    source: Optional[str] = None         # which API provided the data
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @property
    def summary(self) -> str:
        """One-line summary for display."""
        parts = [self.bin]
        if self.scheme:
            parts.append(self.scheme.upper())
        if self.card_type:
            parts.append(self.card_type)
        if self.is_prepaid:
            parts.append("PREPAID")
        if self.issuer_bank:
            parts.append(f"→ {self.issuer_bank}")
        if self.country_code:
            parts.append(f"({self.country_code})")
        return " | ".join(parts)


class BINLookup:
    """
    Multi-source BIN lookup with caching.

    Sources tried in order:
      1. Local cache (in-memory)
      2. Known no-KYC BIN table (hardcoded from research)
      3. binlist.net (free, no key, rate-limited)
      4. freebinchecker.com (free, no key)
    """

    def __init__(self):
        self._cache: dict[str, BINInfo] = {}

    async def lookup(self, bin_number: str) -> BINInfo:
        """
        Look up a BIN (6 or 8 digits). Returns BINInfo with whatever
        data could be found. Never raises — returns error in BINInfo.
        """
        # Normalize: take first 6-8 digits
        bin_clean = bin_number.strip().replace(" ", "").replace("-", "")
        if len(bin_clean) < 6:
            return BINInfo(bin=bin_number, error="BIN must be at least 6 digits")

        bin6 = bin_clean[:6]
        bin8 = bin_clean[:8] if len(bin_clean) >= 8 else bin6

        # Check cache
        if bin8 in self._cache:
            logger.debug(f"Cache hit: {bin8}")
            return self._cache[bin8]
        if bin6 in self._cache:
            logger.debug(f"Cache hit: {bin6}")
            return self._cache[bin6]

        # Try local known BINs first (no network needed)
        info = self._check_known_bins(bin8)
        if info and info.issuer_bank:
            self._cache[bin8] = info
            return info

        # Try API sources
        for lookup_fn in [self._lookup_binlist, self._lookup_freebinchecker]:
            try:
                info = await lookup_fn(bin6)
                if info and info.issuer_bank:
                    info.bin = bin8  # Store the full 8-digit BIN
                    self._cache[bin8] = info
                    return info
            except Exception as e:
                logger.warning(f"Lookup failed ({lookup_fn.__name__}): {e}")
                continue

        # Nothing found
        info = BINInfo(bin=bin8, error="No data found in any source")
        self._cache[bin8] = info
        return info

    async def lookup_batch(self, bins: list[str]) -> list[BINInfo]:
        """Look up multiple BINs with rate-limit-friendly delays."""
        results = []
        for i, bin_num in enumerate(bins):
            info = await self.lookup(bin_num)
            results.append(info)
            # Be polite to free APIs
            if i < len(bins) - 1:
                await asyncio.sleep(2)
        return results

    # ── Source 1: Known no-KYC card BINs ──────────────────────────────

    # These are BIN ranges commonly seen from no-KYC card providers,
    # gathered from community reports and BIN databases.
    # This provides instant results with no API calls.
    KNOWN_BINS = {
        # Sutton Bank (common for fintech/prepaid programs)
        "423768": {"bank": "SUTTON BANK", "country": "US", "type": "prepaid", "scheme": "visa"},
        "421783": {"bank": "SUTTON BANK", "country": "US", "type": "prepaid", "scheme": "visa"},
        "434256": {"bank": "SUTTON BANK", "country": "US", "type": "prepaid", "scheme": "visa"},

        # Metropolitan Commercial Bank (prepaid programs)
        "428837": {"bank": "METROPOLITAN COMMERCIAL BANK", "country": "US", "type": "prepaid", "scheme": "visa"},
        "441112": {"bank": "METROPOLITAN COMMERCIAL BANK", "country": "US", "type": "prepaid", "scheme": "visa"},

        # Fifth Third Bank
        "517805": {"bank": "FIFTH THIRD BANK", "country": "US", "type": "prepaid", "scheme": "mastercard"},

        # Central Trust Bank
        "531993": {"bank": "CENTRAL TRUST BANK", "country": "US", "type": "prepaid", "scheme": "mastercard"},

        # Regions Bank
        "479619": {"bank": "REGIONS BANK", "country": "US", "type": "prepaid", "scheme": "visa"},

        # Peoples Trust Company (Canadian prepaid)
        "516105": {"bank": "PEOPLES TRUST COMPANY", "country": "CA", "type": "prepaid", "scheme": "mastercard"},
        "553691": {"bank": "PEOPLES TRUST COMPANY", "country": "CA", "type": "prepaid", "scheme": "mastercard"},

        # Pathward (formerly MetaBank) — common for US prepaid
        "460007": {"bank": "PATHWARD, N.A. (FKA METABANK)", "country": "US", "type": "prepaid", "scheme": "visa"},
        "476194": {"bank": "PATHWARD, N.A. (FKA METABANK)", "country": "US", "type": "prepaid", "scheme": "visa"},

        # Stride Bank
        "440000": {"bank": "STRIDE BANK, N.A.", "country": "US", "type": "prepaid", "scheme": "visa"},

        # Green Dot / GoBank
        "413295": {"bank": "GREEN DOT BANK", "country": "US", "type": "prepaid", "scheme": "visa"},

        # Canadian issuers for Ezzocard Brown/Teal cards
        "520078": {"bank": "DC PAYMENTS (CANADA)", "country": "CA", "type": "prepaid", "scheme": "mastercard"},
    }

    def _check_known_bins(self, bin_number: str) -> Optional[BINInfo]:
        """Check against hardcoded known BIN table."""
        bin6 = bin_number[:6]
        if bin6 in self.KNOWN_BINS:
            data = self.KNOWN_BINS[bin6]
            return BINInfo(
                bin=bin_number,
                scheme=data.get("scheme"),
                card_type=data.get("type"),
                is_prepaid=data.get("type") == "prepaid",
                issuer_bank=data.get("bank"),
                country_code=data.get("country"),
                source="known_bins_table",
            )
        return None

    # ── Source 2: binlist.net ─────────────────────────────────────────

    async def _lookup_binlist(self, bin6: str) -> Optional[BINInfo]:
        """
        Query binlist.net — free, no API key.
        Rate limit: 5/hr with burst of 5.
        """
        import urllib.request
        import urllib.error

        url = f"https://lookup.binlist.net/{bin6}"
        headers = {
            "Accept-Version": "3",
            "User-Agent": "no-kyc-card-monitor/1.0",
        }

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                logger.warning("binlist.net rate limit hit")
                return None
            raise
        except Exception:
            return None

        bank = data.get("bank", {})
        country = data.get("country", {})

        return BINInfo(
            bin=bin6,
            scheme=data.get("scheme"),
            card_type=data.get("type"),
            category=data.get("brand"),
            is_prepaid=data.get("prepaid"),
            issuer_bank=bank.get("name"),
            issuer_url=bank.get("url"),
            issuer_phone=bank.get("phone"),
            country=country.get("name"),
            country_code=country.get("alpha2"),
            currency=country.get("currency"),
            source="binlist.net",
        )

    # ── Source 3: freebinchecker.com ──────────────────────────────────

    async def _lookup_freebinchecker(self, bin6: str) -> Optional[BINInfo]:
        """
        Query freebinchecker.com — free, no API key.
        """
        import urllib.request
        import urllib.error

        url = f"https://api.freebinchecker.com/bin/{bin6}"
        headers = {"User-Agent": "no-kyc-card-monitor/1.0"}

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError:
            return None
        except Exception:
            return None

        if not data.get("valid"):
            return None

        card = data.get("card", {})
        issuer = data.get("issuer", {})
        country = data.get("country", {})

        return BINInfo(
            bin=bin6,
            scheme=card.get("scheme"),
            card_type=card.get("type"),
            category=card.get("category"),
            issuer_bank=issuer.get("name"),
            issuer_url=issuer.get("url"),
            issuer_phone=issuer.get("tel"),
            country=country.get("name"),
            country_code=country.get("alpha 2 code"),
            currency=country.get("currency"),
            source="freebinchecker.com",
        )

    # ── Add custom BINs ──────────────────────────────────────────────

    def add_known_bin(self, bin6: str, bank: str, country: str = "US",
                      scheme: str = "visa", card_type: str = "prepaid"):
        """Add a BIN to the known table (useful as you discover new ones)."""
        self.KNOWN_BINS[bin6] = {
            "bank": bank, "country": country,
            "scheme": scheme, "type": card_type,
        }
