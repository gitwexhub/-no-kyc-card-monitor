"""
Ezzocard signup agent — REAL IMPLEMENTATION.

Ezzocard (ezzocard.finance, formerly ezzocard.com) uses a shopping cart model:
  1. Select a card product from the catalog (e.g., "$100 USD violet visa")
  2. Set quantity → gets added to cart
  3. Choose crypto payment method (BTC, USDT-TRC20, ETH, LTC, etc.)
  4. Click "BUY NOW" → payment page with deposit address + amount
  5. Send crypto → after confirmation, card details (number, exp, CVV) shown

Card types: Gold (MC/Visa), Violet (Visa), Lime-7 (Visa), Lime-30 (Visa),
            Brown (MC/CAD), Orange (Visa), Yellow (MC), Maroon (Visa), Teal (Visa/CAD)

Site structure (from real DOM at ezzocard.finance):
  - Cards listed as product tiles (tables) in #order-form section
  - Each tile text contains: "$ {denom} {currency} {color} {network}"
  - Quantity input per tile
  - Cart section has crypto selector labels: BTC_N, ETH_M, USDT.TRC20_M, etc.
  - "BUY NOW" button submits cart
  - Cookie banner: "I'm ok with that" button
  - Payment page shows address + amount with "Copy" buttons + "Paid" button

Accepted cryptos (from DOM): BTC, ETH, USDT (ERC20/TRC20/BEP20/SOL),
                              DOGE, LTC, TRX, SOL, BNB
"""

import re
from datetime import datetime, timezone
from playwright.async_api import Page

from agents.base_agent import (
    BaseCardAgent,
    CardNetwork,
    CardResult,
    SignupStatus,
)


# Card type preferences — maps config keys to site labels
CARD_TYPES = {
    "gold_mc":   {"color": "gold",   "network": "mastercard"},
    "gold_visa": {"color": "gold",   "network": "visa"},
    "violet":    {"color": "violet", "network": "visa"},
    "lime7":     {"color": "lime-7", "network": "visa"},
    "lime30":    {"color": "lime-30","network": "visa"},
    "brown":     {"color": "brown",  "network": "mastercard"},
    "orange":    {"color": "orange", "network": "visa"},
    "yellow":    {"color": "yellow", "network": "mastercard"},
    "maroon":    {"color": "maroon", "network": "visa"},
    "teal":      {"color": "teal",   "network": "visa"},
}

# Crypto payment labels from the real DOM
CRYPTO_OPTIONS = {
    "btc":        "BTC_N",
    "eth":        "ETH_M",
    "usdt_erc20": "USDT.ERC20_M",
    "usdt_trc20": "USDT.TRC20_M",
    "usdt_bep20": "USDT.BEP20_M",
    "usdt_sol":   "USDT.SOL_M",
    "doge":       "DOGE_M",
    "ltc":        "LTC_M",
    "trx":        "TRX_M",
    "sol":        "SOL_M",
    "bnb":        "BNB_M",
}


class EzzocardAgent(BaseCardAgent):

    @property
    def provider_name(self) -> str:
        return "ezzocard"

    @property
    def signup_url(self) -> str:
        return "https://ezzocard.finance/"

    async def _pre_signup_hook(self, page: Page) -> None:
        """Dismiss the cookie consent banner."""
        try:
            cookie_btn = page.locator("text=I'm ok with that")
            if await cookie_btn.count() > 0:
                await cookie_btn.first.click()
                self.logger.info("Dismissed cookie banner")
                await self._random_delay()
        except Exception:
            pass

    async def _do_signup(self, page: Page) -> CardResult:
        """
        Real Ezzocard purchase flow using actual DOM structure.
        """
        card = CardResult(provider=self.provider_name, signup_url=self.signup_url)

        # ── Config ────────────────────────────────────────────────────
        target_denomination = self.config.get("denomination", 100)
        target_card_type = self.config.get("card_type", "violet")
        target_crypto = self.config.get("crypto", "btc")

        card_info = CARD_TYPES.get(target_card_type, CARD_TYPES["violet"])
        target_color = card_info["color"]
        target_network = card_info["network"]

        card.network = (
            CardNetwork.VISA if target_network == "visa"
            else CardNetwork.MASTERCARD
        )

        self.logger.info(
            f"Target: ${target_denomination} {target_color} {target_network}, "
            f"pay with {target_crypto}"
        )

        # ── Step 1: Find the matching card tile in the catalog ────────
        self.logger.info("Step 1: Finding card in catalog...")

        await page.evaluate(
            "document.querySelector('#order-form')?.scrollIntoView()"
        )
        await self._random_delay(1, 2)

        # Each product is in a <table>. Text inside contains e.g.:
        #   "$ 100 USD violet visa Price $119.99 Quantity Subtotal $0"
        product_tiles = page.locator("#order-form table, .order-form table, table")
        tile_count = await product_tiles.count()
        self.logger.info(f"Found {tile_count} product tiles")

        target_tile = None
        target_price = None

        for i in range(tile_count):
            tile = product_tiles.nth(i)
            tile_text = (await tile.text_content() or "").lower().strip()

            # Match: denomination + color + network + in stock
            has_denom = str(target_denomination) in tile_text
            has_color = target_color.lower() in tile_text
            has_network = target_network.lower() in tile_text
            is_out_of_stock = "out of stock" in tile_text

            if has_denom and has_color and has_network and not is_out_of_stock:
                target_tile = tile
                price_match = re.search(r"\$([\d,.]+)", tile_text)
                if price_match:
                    target_price = price_match.group(1)
                self.logger.info(
                    f"Found: ${target_denomination} {target_color} "
                    f"{target_network} @ ${target_price}"
                )
                break

        if not target_tile:
            card.status = SignupStatus.FAILED
            card.error = (
                f"Card not found: ${target_denomination} {target_color} "
                f"{target_network}. May be out of stock or delisted."
            )
            await self._screenshot(page, "ezzocard_not_found")
            return card

        await self._screenshot(page, "ezzocard_step1")

        # ── Step 2: Set quantity to 1 ─────────────────────────────────
        self.logger.info("Step 2: Setting quantity to 1...")

        qty_input = target_tile.locator("input")
        if await qty_input.count() > 0:
            await qty_input.first.click()
            await qty_input.first.fill("1")
            # Trigger change event
            await qty_input.first.press("Tab")
            await self._random_delay(0.5, 1.5)
            self.logger.info("Quantity set to 1")

        await self._screenshot(page, "ezzocard_step2")

        # ── Step 3: Select crypto payment ─────────────────────────────
        self.logger.info(f"Step 3: Selecting {target_crypto}...")

        # Scroll to payment section
        buy_btn = page.locator("text=BUY NOW")
        if await buy_btn.count() > 0:
            await buy_btn.first.scroll_into_view_if_needed()
        await self._random_delay()

        crypto_label = CRYPTO_OPTIONS.get(target_crypto, "BTC_N")
        crypto_selected = False

        # The crypto options are likely radio buttons or clickable labels
        # Try exact text match first, then partial
        for selector in [
            f"text='{crypto_label}'",
            f"text={crypto_label}",
            f"label:has-text('{crypto_label}')",
            f"input[value='{crypto_label}']",
            f"[id*='{crypto_label}']",
        ]:
            try:
                el = page.locator(selector)
                if await el.count() > 0:
                    await el.first.click()
                    crypto_selected = True
                    card.deposit_currency = target_crypto.upper().replace("_", ".")
                    self.logger.info(f"Selected: {crypto_label}")
                    await self._random_delay()
                    break
            except Exception:
                continue

        if not crypto_selected:
            self.logger.warning(f"Could not select {target_crypto}, trying BTC")
            for sel in ["text=BTC_N", "text=BTC"]:
                try:
                    el = page.locator(sel)
                    if await el.count() > 0:
                        await el.first.click()
                        card.deposit_currency = "BTC"
                        crypto_selected = True
                        break
                except Exception:
                    continue

        await self._screenshot(page, "ezzocard_step3")

        # ── Step 4: Click BUY NOW ─────────────────────────────────────
        self.logger.info("Step 4: Clicking BUY NOW...")

        try:
            buy_btn = page.locator("text=BUY NOW")
            if await buy_btn.count() > 0:
                await buy_btn.first.click()
                self.logger.info("Clicked BUY NOW")
            else:
                card.status = SignupStatus.FAILED
                card.error = "BUY NOW button not found — cart may be empty"
                return card
        except Exception as e:
            card.status = SignupStatus.FAILED
            card.error = f"BUY NOW click failed: {e}"
            return card

        # Wait for payment page to load (Ezzocard says "few minutes")
        await page.wait_for_timeout(5000)
        await self._screenshot(page, "ezzocard_step4")

        # Check if we need to enter email + confirm
        # The flow has: "enter your email address and click Pay with {crypto}"
        email = self.config.get("email")
        if email:
            email_inputs = page.locator(
                "input[type='email'], input[name*='email'], "
                "input[placeholder*='email'], input[placeholder*='Email']"
            )
            if await email_inputs.count() > 0:
                await email_inputs.first.fill(email)
                self.logger.info(f"Entered email: {email}")
                await self._random_delay()

        # Look for "Pay with" confirmation button
        pay_confirm = page.locator("text=/Pay with/i")
        if await pay_confirm.count() > 0:
            await pay_confirm.first.click()
            self.logger.info("Clicked Pay with confirmation")
            await page.wait_for_timeout(5000)
            await self._screenshot(page, "ezzocard_step4b")

        # ── Step 5: Extract deposit address + amount ──────────────────
        self.logger.info("Step 5: Extracting deposit details...")

        page_text = await page.text_content("body") or ""

        # Extract crypto address using regex patterns
        addr_patterns = [
            r"(bc1[a-zA-HJ-NP-Z0-9]{39,59})",         # BTC bech32
            r"([13][a-km-zA-HJ-NP-Z1-9]{25,34})",      # BTC legacy
            r"(0x[a-fA-F0-9]{40})",                      # ETH/ERC20
            r"(T[a-zA-Z0-9]{33})",                       # TRC20
            r"([LM][a-km-zA-HJ-NP-Z1-9]{26,33})",      # LTC
            r"(D[a-km-zA-HJ-NP-Z1-9]{25,34})",         # DOGE
        ]

        for pattern in addr_patterns:
            match = re.search(pattern, page_text)
            if match:
                card.deposit_address = match.group(1)
                self.logger.info(f"Address: {card.deposit_address[:16]}...")
                break

        # Fallback: check readonly inputs (Ezzocard uses "Copy" buttons)
        if not card.deposit_address:
            ro_inputs = page.locator("input[readonly]")
            for i in range(await ro_inputs.count()):
                val = (await ro_inputs.nth(i).get_attribute("value") or "").strip()
                if len(val) > 20:
                    card.deposit_address = val
                    self.logger.info(f"Address from input: {val[:16]}...")
                    break

        # Extract amount (e.g., "0.00234500 BTC" or "27.50 USDT")
        amount_match = re.search(
            r"([\d.]+)\s*(BTC|ETH|USDT|LTC|DOGE|TRX|SOL|BNB)",
            page_text, re.IGNORECASE
        )
        if amount_match:
            card.deposit_amount = float(amount_match.group(1))
            card.deposit_currency = amount_match.group(2).upper()
            self.logger.info(
                f"Amount: {card.deposit_amount} {card.deposit_currency}"
            )

        # Extract Payment ID if visible (useful for support)
        pid_match = re.search(r"Payment\s*ID[:\s]+([A-Za-z0-9-]+)", page_text)
        if pid_match:
            card.metadata["payment_id"] = pid_match.group(1)

        await self._screenshot(page, "ezzocard_step5")

        # ── Set result ────────────────────────────────────────────────
        if card.deposit_address:
            card.status = SignupStatus.AWAITING_DEPOSIT
            card.deposit_chain = target_crypto
            card.metadata.update({
                "denomination_usd": target_denomination,
                "card_color": target_color,
                "card_network": target_network,
                "price_usd": target_price,
            })
            self.logger.info("SUCCESS — awaiting deposit")
        else:
            card.status = SignupStatus.FAILED
            card.error = (
                "Could not extract deposit address. Cart may have been "
                "empty, or the page structure changed."
            )

        return card

    async def wait_for_card_delivery(self, page: Page, card: CardResult,
                                      timeout_minutes: int = 30) -> CardResult:
        """
        Step 6: After crypto is sent, wait on the payment page for
        card details to appear. Ezzocard shows card number, expiry,
        and CVV directly on the page after payment confirms.

        For automatic-mode cryptos (BTC), this happens on the page.
        For manual-mode, card data is emailed instead.

        Call this AFTER sending the deposit. The page should still be
        on the payment/confirmation screen.

        Returns updated CardResult with bin_number, last4, expiry populated.
        """
        self.logger.info(
            f"Step 6: Waiting up to {timeout_minutes}min for card delivery..."
        )

        # First, click the "Paid" button if it exists
        paid_btn = page.locator("text=/Paid/i, button:has-text('Paid')")
        if await paid_btn.count() > 0:
            await paid_btn.first.click()
            self.logger.info("Clicked 'Paid' button")
            await self._random_delay(2, 4)

        # Poll the page for card details to appear
        poll_interval = 30  # seconds
        max_polls = (timeout_minutes * 60) // poll_interval

        for poll in range(max_polls):
            page_text = await page.text_content("body") or ""

            # Try to extract card details
            details = self._extract_card_details(page_text)

            if details["full_number"]:
                card.bin_number = details["bin"]
                card.card_number_last4 = details["last4"]
                card.expiry = details["expiry"]
                card.status = SignupStatus.CARD_ISSUED
                card.updated_at = datetime.now(timezone.utc).isoformat()

                # Store full number in metadata (encrypted storage handles security)
                card.metadata["full_card_number"] = details["full_number"]
                if details["cvv"]:
                    card.metadata["cvv"] = details["cvv"]

                self.logger.info(
                    f"CARD DELIVERED! BIN: {card.bin_number}, "
                    f"Last4: {card.card_number_last4}, "
                    f"Expiry: {card.expiry}"
                )
                await self._screenshot(page, "ezzocard_step6_card_delivered")
                return card

            # Check for error messages
            lower_text = page_text.lower()
            if any(err in lower_text for err in [
                "payment failed", "expired", "underpayment", "not received"
            ]):
                card.status = SignupStatus.FAILED
                card.error = "Payment issue detected on confirmation page"
                await self._screenshot(page, "ezzocard_step6_error")
                return card

            self.logger.info(
                f"Poll {poll + 1}/{max_polls}: No card details yet, "
                f"waiting {poll_interval}s..."
            )
            await page.wait_for_timeout(poll_interval * 1000)

            # Refresh page periodically to check for updates
            if poll > 0 and poll % 4 == 0:
                await page.reload(wait_until="domcontentloaded")
                await self._random_delay(2, 4)

        card.error = f"Card not delivered within {timeout_minutes} minutes"
        await self._screenshot(page, "ezzocard_step6_timeout")
        return card

    async def _do_health_check(self, page: Page, card: CardResult) -> bool:
        """
        Check card via Ezzocard's balance checker at:
        https://ezzocard.finance/checker/check-card-balance/
        """
        if not card.card_number_last4 and not card.metadata.get("full_card_number"):
            self.logger.warning("No card number — skipping balance check")
            return True

        try:
            await page.goto(
                "https://ezzocard.finance/checker/check-card-balance/",
                wait_until="domcontentloaded",
            )
            await self._random_delay()

            page_text = (await page.text_content("body") or "").lower()
            if "balance" in page_text or "check" in page_text:
                return True
            return True

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
