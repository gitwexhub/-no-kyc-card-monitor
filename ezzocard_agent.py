"""
Ezzocard signup agent.

Ezzocard (ezzocard.com) offers both Visa and Mastercard virtual cards
with no KYC. Signup is web-based: pick card type → get deposit address
→ send crypto → card issued.

This is a REFERENCE IMPLEMENTATION showing how to build a provider agent.
You will need to inspect the actual Ezzocard signup flow and update
selectors as they change.
"""

from playwright.async_api import Page

from agents.base_agent import (
    BaseCardAgent,
    CardNetwork,
    CardResult,
    SignupStatus,
)


class EzzocardAgent(BaseCardAgent):

    @property
    def provider_name(self) -> str:
        return "ezzocard"

    @property
    def signup_url(self) -> str:
        return "https://ezzocard.com"

    async def _pre_signup_hook(self, page: Page) -> None:
        """Dismiss any cookie banners or popups."""
        try:
            cookie_btn = page.locator("button:has-text('Accept'), .cookie-accept")
            if await cookie_btn.count() > 0:
                await cookie_btn.first.click()
                await self._random_delay()
        except Exception:
            pass  # No cookie banner, continue

    async def _do_signup(self, page: Page) -> CardResult:
        """
        Walk through the Ezzocard signup flow.

        Typical flow:
        1. Landing page → click "Get Card" / "Buy Card"
        2. Select card denomination / type (Visa or Mastercard)
        3. Choose crypto payment method (BTC, LTC, USDT, etc.)
        4. Receive deposit address + amount
        5. (External) Send crypto to deposit address
        6. Wait for confirmation → card details shown

        NOTE: Selectors below are EXAMPLES. You must inspect the actual
        site and update these. Sites change frequently.
        """
        card = CardResult(provider=self.provider_name, signup_url=self.signup_url)

        # ── Step 1: Navigate to card purchase ─────────────────────────
        self.logger.info("Step 1: Looking for card purchase button...")

        # Try common button patterns
        buy_selectors = [
            "a:has-text('Get Card')",
            "a:has-text('Buy Card')",
            "button:has-text('Get Started')",
            "a:has-text('Order')",
            "[href*='order']",
            "[href*='buy']",
        ]
        for sel in buy_selectors:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    await el.first.click()
                    await self._random_delay(1, 3)
                    break
            except Exception:
                continue

        await self._screenshot(page, "ezzocard_step1")

        # ── Step 2: Select card type ──────────────────────────────────
        self.logger.info("Step 2: Selecting card type...")

        # Prefer Visa, fall back to Mastercard
        card_type_selectors = [
            ("[data-card='visa']", CardNetwork.VISA),
            ("button:has-text('Visa')", CardNetwork.VISA),
            (".card-type-visa", CardNetwork.VISA),
            ("[data-card='mastercard']", CardNetwork.MASTERCARD),
            ("button:has-text('Mastercard')", CardNetwork.MASTERCARD),
            (".card-type-mastercard", CardNetwork.MASTERCARD),
        ]

        for sel, network in card_type_selectors:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    await el.first.click()
                    card.network = network
                    self.logger.info(f"Selected {network.value} card")
                    await self._random_delay()
                    break
            except Exception:
                continue

        # Select denomination if needed (e.g. $25, $50, $100, $200)
        denomination = self.config.get("denomination", 25)
        denom_selectors = [
            f"button:has-text('${denomination}')",
            f"[data-amount='{denomination}']",
            f"option[value='{denomination}']",
        ]
        for sel in denom_selectors:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    await el.first.click()
                    await self._random_delay()
                    break
            except Exception:
                continue

        await self._screenshot(page, "ezzocard_step2")

        # ── Step 3: Select crypto payment ─────────────────────────────
        self.logger.info("Step 3: Selecting payment method...")

        preferred_crypto = self.config.get("crypto", "btc")
        crypto_selectors = [
            f"button:has-text('{preferred_crypto.upper()}')",
            f"[data-crypto='{preferred_crypto}']",
            f"img[alt*='{preferred_crypto}']",
        ]
        for sel in crypto_selectors:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    await el.first.click()
                    await self._random_delay()
                    break
            except Exception:
                continue

        await self._screenshot(page, "ezzocard_step3")

        # ── Step 4: Extract deposit details ───────────────────────────
        self.logger.info("Step 4: Extracting deposit address...")

        # Wait for deposit info to appear
        await page.wait_for_timeout(3000)

        # Try to find the deposit address (usually a long alphanumeric string
        # displayed in a code block, input field, or QR section)
        address_selectors = [
            ".deposit-address",
            "[data-deposit-address]",
            "input[readonly][value]",
            ".address-text",
            "code",
        ]
        for sel in address_selectors:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    addr = await el.first.get_attribute("value") or await el.first.text_content()
                    addr = addr.strip()
                    if len(addr) > 20:  # Looks like an address
                        card.deposit_address = addr
                        card.deposit_chain = preferred_crypto
                        self.logger.info(f"Deposit address: {addr[:12]}...{addr[-6:]}")
                        break
            except Exception:
                continue

        # Try to find the required amount
        amount_selectors = [
            ".deposit-amount",
            "[data-amount]",
            ".payment-amount",
        ]
        for sel in amount_selectors:
            try:
                el = page.locator(sel)
                if await el.count() > 0:
                    amount_text = await el.first.text_content()
                    # Parse number from text like "0.00045 BTC" or "$27.50"
                    import re
                    numbers = re.findall(r"[\d.]+", amount_text)
                    if numbers:
                        card.deposit_amount = float(numbers[0])
                        card.deposit_currency = preferred_crypto.upper()
                        break
            except Exception:
                continue

        await self._screenshot(page, "ezzocard_step4_deposit")

        if card.deposit_address:
            card.status = SignupStatus.AWAITING_DEPOSIT
            card.metadata["denomination_usd"] = denomination
        else:
            card.status = SignupStatus.FAILED
            card.error = "Could not extract deposit address"

        return card

    async def _do_health_check(self, page: Page, card: CardResult) -> bool:
        """
        Check if card is still active by visiting Ezzocard's
        balance check / card status page.
        """
        # Ezzocard may have a status check page or dashboard
        check_url = self.config.get(
            "status_url", "https://ezzocard.com/check"
        )
        try:
            await page.goto(check_url, wait_until="domcontentloaded")
            await self._random_delay()

            # Look for indicators the card is active
            active_indicators = [
                "text=Active",
                "text=Valid",
                ".status-active",
                ".card-active",
            ]
            for sel in active_indicators:
                try:
                    el = page.locator(sel)
                    if await el.count() > 0:
                        return True
                except Exception:
                    continue

            # Look for frozen/disabled indicators
            frozen_indicators = [
                "text=Frozen",
                "text=Disabled",
                "text=Suspended",
                ".status-frozen",
            ]
            for sel in frozen_indicators:
                try:
                    el = page.locator(sel)
                    if await el.count() > 0:
                        return False
                except Exception:
                    continue

            return True  # Assume active if no clear signal

        except Exception as e:
            self.logger.error(f"Health check navigation failed: {e}")
            return False
