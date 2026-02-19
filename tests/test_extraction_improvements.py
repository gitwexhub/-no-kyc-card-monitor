"""
Tests for the data extraction accuracy improvements.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import unittest
from unittest.mock import patch, MagicMock

from search_sources import (
    extract_card_name,
    extract_company_from_snippet,
    extract_company_website,
    fetch_app_store_metadata,
    fetch_play_store_metadata,
    serpapi_search,
)


class TestExtractCardName(unittest.TestCase):
    """Tests for improved extract_card_name function."""

    def test_skips_generic_visa(self):
        """Should not return just 'Visa' as card name."""
        result = extract_card_name("Cheapest Visa Card", "Get your Visa debit card today")
        self.assertNotEqual(result.lower(), "visa")
        self.assertNotIn("cheapest", result.lower())

    def test_skips_generic_debit(self):
        """Should not return just 'Debit' as card name."""
        result = extract_card_name("Best Debit Card", "Anonymous debit card")
        self.assertNotEqual(result.lower(), "debit")

    def test_extracts_camelcase_names(self):
        """Should extract CamelCase app names like BitPay."""
        result = extract_card_name("BitPay Card - Visa Debit", "Use your crypto with BitPay")
        self.assertEqual(result, "BitPay")

    def test_extracts_camelcase_cashapp(self):
        """Should extract CashApp style names."""
        result = extract_card_name("CashApp Visa Card", "Send money with CashApp")
        self.assertEqual(result, "CashApp")

    def test_filters_marketing_adjectives(self):
        """Should filter marketing words from fallback title."""
        result = extract_card_name("Best Anonymous No KYC Visa Card", "")
        self.assertNotIn("best", result.lower())
        self.assertNotIn("anonymous", result.lower())
        self.assertNotIn("no kyc", result.lower())

    def test_extracts_real_product_name(self):
        """Should extract actual product names."""
        result = extract_card_name("Revolut Card - Virtual Visa", "Get Revolut card")
        # Should find Revolut, not generic terms
        self.assertIn("Revolut", result)


class TestExtractCompanyFromSnippet(unittest.TestCase):
    """Tests for improved extract_company_from_snippet function."""

    def test_skips_google_llc(self):
        """Should not return Google LLC as company."""
        result = extract_company_from_snippet(
            "Crypto Card App",
            "Offered by Google LLC on Play Store"
        )
        self.assertNotEqual(result.lower(), "google llc")
        self.assertNotEqual(result.lower(), "google")

    def test_skips_apple_inc(self):
        """Should not return Apple Inc as company."""
        result = extract_company_from_snippet(
            "Card App on App Store",
            "by Apple Inc"
        )
        self.assertNotEqual(result.lower(), "apple inc")
        self.assertNotEqual(result.lower(), "apple")

    def test_extracts_developed_by(self):
        """Should extract company from 'developed by' pattern."""
        result = extract_company_from_snippet(
            "Crypto Card App",
            "developed by Fintech Solutions"
        )
        self.assertEqual(result, "Fintech Solutions")

    def test_extracts_company_suffix(self):
        """Should extract company with Inc/LLC suffix."""
        result = extract_company_from_snippet(
            "Card from Payments Corp",
            "Secure payments by Payments Corp"
        )
        self.assertIn("Payments", result)


class TestExtractCompanyWebsite(unittest.TestCase):
    """Tests for improved extract_company_website function."""

    def test_returns_empty_for_app_store(self):
        """Should return empty for App Store platform."""
        result = extract_company_website(
            "https://apps.apple.com/app/mycard/id123",
            "Some snippet",
            "App Store"
        )
        self.assertEqual(result, "")

    def test_returns_empty_for_google_play(self):
        """Should return empty for Google Play platform."""
        result = extract_company_website(
            "https://play.google.com/store/apps/details?id=com.mycard",
            "Some snippet",
            "Google Play"
        )
        self.assertEqual(result, "")

    def test_extracts_domain_for_web(self):
        """Should extract base domain for Web platform."""
        result = extract_company_website(
            "https://example.com/cards/visa",
            "Some snippet",
            "Web (example.com)"
        )
        self.assertEqual(result, "https://example.com")


class TestFetchAppStoreMetadata(unittest.TestCase):
    """Tests for fetch_app_store_metadata function."""

    @patch('search_sources.requests.get')
    def test_extracts_app_name_from_title(self, mock_get):
        """Should extract app name from page title."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>MyCard Wallet on the App Store</title></head>
        <body></body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_app_store_metadata("https://apps.apple.com/app/mycard/id123")
        self.assertEqual(result["app_name"], "MyCard Wallet")

    @patch('search_sources.requests.get')
    def test_extracts_developer_name(self, mock_get):
        """Should extract developer name."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>MyCard on the App Store</title></head>
        <body>
        <a href="/developer/fintech-inc">Fintech Inc</a>
        </body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_app_store_metadata("https://apps.apple.com/app/mycard/id123")
        self.assertEqual(result["developer_name"], "Fintech Inc")

    @patch('search_sources.requests.get')
    def test_extracts_seller_name_json(self, mock_get):
        """Should extract seller name from JSON-LD."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>MyCard on the App Store</title></head>
        <body>
        "sellerName": "CardTech LLC"
        </body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_app_store_metadata("https://apps.apple.com/app/mycard/id123")
        self.assertEqual(result["developer_name"], "CardTech LLC")

    @patch('search_sources.requests.get')
    def test_skips_apple_website(self, mock_get):
        """Should not return apple.com as developer website."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>MyCard on the App Store</title></head>
        <body>
        <a href="https://apple.com/support">Website</a>
        </body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_app_store_metadata("https://apps.apple.com/app/mycard/id123")
        self.assertEqual(result["developer_website"], "")

    @patch('search_sources.requests.get')
    def test_extracts_developer_website(self, mock_get):
        """Should extract non-Apple developer website."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>MyCard on the App Store</title></head>
        <body>
        <a href="https://mycard.io">Website</a>
        </body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_app_store_metadata("https://apps.apple.com/app/mycard/id123")
        self.assertEqual(result["developer_website"], "https://mycard.io")


class TestFetchPlayStoreMetadata(unittest.TestCase):
    """Tests for fetch_play_store_metadata function."""

    @patch('search_sources.requests.get')
    def test_extracts_app_name_from_title(self, mock_get):
        """Should extract app name from page title."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>CryptoCard Wallet - Apps on Google Play</title></head>
        <body></body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_play_store_metadata("https://play.google.com/store/apps/details?id=com.crypto")
        self.assertEqual(result["app_name"], "CryptoCard Wallet")

    @patch('search_sources.requests.get')
    def test_extracts_developer_name(self, mock_get):
        """Should extract developer name."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>MyCard - Apps on Google Play</title></head>
        <body>
        <a href="/store/apps/developer?id=CardCompany">CardCompany</a>
        </body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_play_store_metadata("https://play.google.com/store/apps/details?id=com.mycard")
        self.assertEqual(result["developer_name"], "CardCompany")

    @patch('search_sources.requests.get')
    def test_skips_google_llc(self, mock_get):
        """Should not return Google LLC as developer."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>MyCard - Apps on Google Play</title></head>
        <body>
        <a href="/store/apps/developer?id=Google">Google LLC</a>
        </body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_play_store_metadata("https://play.google.com/store/apps/details?id=com.mycard")
        self.assertEqual(result["developer_name"], "")

    @patch('search_sources.requests.get')
    def test_skips_google_website(self, mock_get):
        """Should not return google.com as developer website."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>MyCard - Apps on Google Play</title></head>
        <body>
        <a href="https://google.com/support">Visit website</a>
        </body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_play_store_metadata("https://play.google.com/store/apps/details?id=com.mycard")
        self.assertEqual(result["developer_website"], "")

    @patch('search_sources.requests.get')
    def test_extracts_developer_website(self, mock_get):
        """Should extract non-Google developer website."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <head><title>MyCard - Apps on Google Play</title></head>
        <body>
        <a href="https://mycard.com">Visit website</a>
        </body>
        </html>
        '''
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_play_store_metadata("https://play.google.com/store/apps/details?id=com.mycard")
        self.assertEqual(result["developer_website"], "https://mycard.com")


class TestSerpApiSearchIntegration(unittest.TestCase):
    """Integration tests for serpapi_search with metadata fetching."""

    @patch('search_sources.fetch_app_store_metadata')
    @patch('search_sources.requests.get')
    def test_uses_app_store_metadata_for_website(self, mock_get, mock_fetch_metadata):
        """Should use App Store metadata for developer website."""
        # Mock SerpAPI response
        mock_serp_response = MagicMock()
        mock_serp_response.json.return_value = {
            "organic_results": [{
                "title": "Crypto Card on the App Store",
                "snippet": "No KYC Visa card for crypto",
                "link": "https://apps.apple.com/app/crypto-card/id123",
                "displayed_link": "apps.apple.com"
            }]
        }
        mock_serp_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_serp_response

        # Mock metadata fetch
        mock_fetch_metadata.return_value = {
            "app_name": "CryptoCard Pro",
            "developer_name": "Fintech Inc",
            "developer_website": "https://cryptocard.io"
        }

        results = serpapi_search("no kyc visa card", "fake_api_key")

        self.assertEqual(len(results), 1)
        # card_name and company_name are now empty (will be filled by Claude)
        self.assertEqual(results[0]["card_name"], "")
        self.assertEqual(results[0]["company_name"], "")
        # But website should be extracted from metadata
        self.assertEqual(results[0]["company_website"], "https://cryptocard.io")

    @patch('search_sources.fetch_play_store_metadata')
    @patch('search_sources.requests.get')
    def test_uses_play_store_metadata_for_website(self, mock_get, mock_fetch_metadata):
        """Should use Play Store metadata for developer website."""
        # Mock SerpAPI response
        mock_serp_response = MagicMock()
        mock_serp_response.json.return_value = {
            "organic_results": [{
                "title": "Bitcoin Card - Apps on Google Play",
                "snippet": "Anonymous Visa debit card",
                "link": "https://play.google.com/store/apps/details?id=com.btccard",
                "displayed_link": "play.google.com"
            }]
        }
        mock_serp_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_serp_response

        # Mock metadata fetch
        mock_fetch_metadata.return_value = {
            "app_name": "BitCard Wallet",
            "developer_name": "BitCard Ltd",
            "developer_website": "https://bitcard.com"
        }

        results = serpapi_search("anonymous visa card", "fake_api_key")

        self.assertEqual(len(results), 1)
        # card_name and company_name are now empty (will be filled by Claude)
        self.assertEqual(results[0]["card_name"], "")
        self.assertEqual(results[0]["company_name"], "")
        # But website should be extracted from metadata
        self.assertEqual(results[0]["company_website"], "https://bitcard.com")

    @patch('search_sources.fetch_app_store_metadata')
    @patch('search_sources.requests.get')
    def test_empty_website_when_metadata_fails(self, mock_get, mock_fetch_metadata):
        """Should have empty website when metadata fetch fails."""
        # Mock SerpAPI response
        mock_serp_response = MagicMock()
        mock_serp_response.json.return_value = {
            "organic_results": [{
                "title": "Card App on App Store",
                "snippet": "No KYC Visa card",
                "link": "https://apps.apple.com/app/card/id456",
                "displayed_link": "apps.apple.com"
            }]
        }
        mock_serp_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_serp_response

        # Mock metadata fetch failure
        mock_fetch_metadata.return_value = None

        results = serpapi_search("no kyc visa card", "fake_api_key")

        self.assertEqual(len(results), 1)
        # Website should be empty since it's App Store and metadata failed
        self.assertEqual(results[0]["company_website"], "")


class TestEnrichmentFallback(unittest.TestCase):
    """Tests for enrichment fallback logic."""

    @patch('enrich.fetch_app_store_metadata')
    def test_enrichment_uses_fallback_when_website_fails(self, mock_fetch):
        """Should use App Store metadata as fallback when website can't be fetched."""
        from enrich import enrich_result

        mock_fetch.return_value = {
            "app_name": "TestCard",
            "developer_name": "Test Company",
            "developer_website": "https://testcard.io"
        }

        result = {
            "source_platform": "App Store",
            "source_url": "https://apps.apple.com/app/test/id789",
            "company_website": "",
            "company_name": "",
            "card_name": "",
            "notes": ""
        }

        # Website fetch fails, so fallback to metadata
        with patch('enrich.fetch_page', return_value=None):
            enriched = enrich_result(result)

        # Should get website from metadata
        self.assertEqual(enriched["company_website"], "https://testcard.io")
        # Should use fallback values for company/card since website couldn't be fetched
        # (Claude enrichment didn't run because fetch_page returned None)

    @patch('enrich.fetch_app_store_metadata')
    @patch('enrich.fetch_page')
    @patch('enrich.analyze_with_claude')
    def test_enrichment_derives_names_from_domain(self, mock_claude, mock_fetch_page, mock_fetch_meta):
        """Should derive company_name from domain when Claude returns nothing."""
        from enrich import enrich_result

        mock_fetch_meta.return_value = None
        mock_fetch_page.return_value = "<html><body>Some content</body></html>"
        mock_claude.return_value = {}  # Claude returns empty

        result = {
            "source_platform": "Web (example.com)",
            "source_url": "https://example.com/card",
            "company_website": "https://example.com",
            "company_name": "",
            "card_name": "",
            "notes": ""
        }

        enriched = enrich_result(result)

        # Should derive company name from domain
        self.assertEqual(enriched["company_name"], "Example")
        # Should derive card name from company name
        self.assertEqual(enriched["card_name"], "Example Card")


if __name__ == "__main__":
    unittest.main(verbosity=2)
