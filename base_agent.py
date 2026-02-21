"""
Base agent class for no-KYC card signup automation.

Every provider agent must inherit from BaseCardAgent and implement
the abstract methods. The base class handles:
  - Browser lifecycle (Playwright)
  - Logging & screenshots
  - Retry logic with exponential backoff
  - Card storage interface
  - Health-check framework
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
import asyncio
import json
import logging
import uuid

from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class SignupStatus(Enum):
    PENDING = "pending"
    EMAIL_SENT = "email_sent"
    AWAITING_DEPOSIT = "awaiting_deposit"
    DEPOSIT_SENT = "deposit_sent"
    CARD_ISSUED = "card_issued"
    FAILED = "failed"
    FROZEN = "frozen"


class CardNetwork(Enum):
    VISA = "visa"
    MASTERCARD = "mastercard"
    UNKNOWN = "unknown"


@dataclass
class CardResult:
    """Represents a successfully issued card (or attempt)."""
    provider: str
    card_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    status: SignupStatus = SignupStatus.PENDING
    network: CardNetwork = CardNetwork.UNKNOWN
    card_number_last4: Optional[str] = None
    expiry: Optional[str] = None
    balance: float = 0.0
    deposit_address: Optional[str] = None
    deposit_chain: Optional[str] = None
    deposit_amount: Optional[float] = None
    deposit_currency: Optional[str] = None
    signup_url: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["network"] = self.network.value
        return d


class BaseCardAgent(ABC):
    """
    Abstract base for all provider signup agents.

    Subclasses must implement:
        - provider_name (property)
        - signup_url (property)
        - _do_signup(page) -> CardResult
        - _do_health_check(page, card) -> bool

    Optional overrides:
        - _pre_signup_hook(page)  — e.g. dismiss cookie banners
        - _post_signup_hook(page, card)  — e.g. screenshot confirmation
        - browser_args  — extra Playwright launch args
    """

    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 5  # seconds
    SCREENSHOT_DIR = Path("logs/screenshots")
    DEFAULT_TIMEOUT = 30_000  # ms

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger(f"agent.{self.provider_name}")
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Abstract interface ────────────────────────────────────────────

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique slug for this provider, e.g. 'ezzocard', 'solcard'."""
        ...

    @property
    @abstractmethod
    def signup_url(self) -> str:
        """Starting URL for the signup flow."""
        ...

    @abstractmethod
    async def _do_signup(self, page: Page) -> CardResult:
        """
        Core signup logic. Navigate the provider's flow and return a CardResult.
        The page is already at self.signup_url when this is called.
        """
        ...

    @abstractmethod
    async def _do_health_check(self, page: Page, card: CardResult) -> bool:
        """
        Check if a previously issued card is still active.
        Return True if card is healthy, False if frozen/dead.
        """
        ...

    # ── Optional hooks ────────────────────────────────────────────────

    async def _pre_signup_hook(self, page: Page) -> None:
        """Override to handle cookie banners, popups, etc."""
        pass

    async def _post_signup_hook(self, page: Page, card: CardResult) -> None:
        """Override for post-signup actions like screenshots."""
        await self._screenshot(page, f"{self.provider_name}_signup_complete")

    @property
    def browser_args(self) -> list[str]:
        """Extra Playwright chromium launch args."""
        return []

    # ── Browser lifecycle ─────────────────────────────────────────────

    async def _launch_browser(self) -> Browser:
        """Launch a stealth-configured browser."""
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(
            headless=self.config.get("headless", True),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                *self.browser_args,
            ],
        )
        return self._browser

    async def _new_context(self) -> BrowserContext:
        """Create a browser context with anti-detection settings."""
        if not self._browser:
            await self._launch_browser()

        proxy = self.config.get("proxy")
        proxy_config = {"server": proxy} if proxy else None

        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
            proxy=proxy_config,
        )
        # Mask webdriver flag
        await self._context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            """
        )
        return self._context

    async def _close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()

    # ── Core signup with retries ──────────────────────────────────────

    async def signup(self) -> CardResult:
        """
        Run the full signup flow with retries and error handling.
        Returns a CardResult regardless of success/failure.
        """
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self.logger.info(
                    f"Signup attempt {attempt}/{self.MAX_RETRIES} "
                    f"for {self.provider_name}"
                )
                ctx = await self._new_context()
                page = await ctx.new_page()
                page.set_default_timeout(self.DEFAULT_TIMEOUT)

                # Navigate to signup
                await page.goto(self.signup_url, wait_until="domcontentloaded")
                await self._pre_signup_hook(page)

                # Run provider-specific signup
                card = await self._do_signup(page)

                # Post-signup
                await self._post_signup_hook(page, card)
                await self._close()

                self.logger.info(
                    f"Signup succeeded for {self.provider_name}: "
                    f"status={card.status.value}"
                )
                return card

            except Exception as e:
                last_error = str(e)
                self.logger.warning(
                    f"Attempt {attempt} failed for {self.provider_name}: {e}"
                )
                await self._close()

                if attempt < self.MAX_RETRIES:
                    wait = self.RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    self.logger.info(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)

        # All retries exhausted
        self.logger.error(
            f"All {self.MAX_RETRIES} attempts failed for {self.provider_name}"
        )
        return CardResult(
            provider=self.provider_name,
            status=SignupStatus.FAILED,
            error=last_error,
        )

    # ── Health check ──────────────────────────────────────────────────

    async def health_check(self, card: CardResult) -> bool:
        """Check if a card is still active. Updates card status if frozen."""
        try:
            ctx = await self._new_context()
            page = await ctx.new_page()
            healthy = await self._do_health_check(page, card)
            await self._close()

            if not healthy:
                card.status = SignupStatus.FROZEN
                card.updated_at = datetime.now(timezone.utc).isoformat()
                self.logger.warning(
                    f"Card {card.card_id} on {self.provider_name} is FROZEN"
                )
            return healthy

        except Exception as e:
            self.logger.error(f"Health check failed for {card.card_id}: {e}")
            await self._close()
            return False

    # ── Utilities ─────────────────────────────────────────────────────

    async def _screenshot(self, page: Page, name: str) -> Path:
        """Save a screenshot for debugging."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.SCREENSHOT_DIR / f"{name}_{ts}.png"
        await page.screenshot(path=str(path), full_page=True)
        self.logger.debug(f"Screenshot saved: {path}")
        return path

    async def _wait_and_click(self, page: Page, selector: str, timeout: int = None):
        """Wait for an element and click it."""
        timeout = timeout or self.DEFAULT_TIMEOUT
        await page.wait_for_selector(selector, timeout=timeout)
        await page.click(selector)

    async def _fill_field(self, page: Page, selector: str, value: str):
        """Clear and fill a form field."""
        await page.wait_for_selector(selector)
        await page.fill(selector, value)

    async def _random_delay(self, min_s: float = 0.5, max_s: float = 2.0):
        """Human-like random delay between actions."""
        import random
        await asyncio.sleep(random.uniform(min_s, max_s))

    def __repr__(self):
        return f"<{self.__class__.__name__} provider={self.provider_name}>"
