"""
Telegram bot agent — base class for providers that use Telegram bots
as their signup interface (e.g., ZeroID CC, some Trocador flows).

Requires: pip install telethon

You must provide your own Telegram API credentials (api_id, api_hash)
from https://my.telegram.org — these are NOT the same as a bot token.
"""

import asyncio
import logging
import re
from typing import Optional

from agents.base_agent import BaseCardAgent, CardResult, SignupStatus, CardNetwork


class TelegramBotAgent(BaseCardAgent):
    """
    Base class for Telegram-bot-based card providers.

    Subclasses must set:
        - provider_name
        - bot_username  (e.g., "@ZeroID_bot")
        - And override _parse_bot_flow()

    Config must include:
        - telegram_api_id: int
        - telegram_api_hash: str
        - telegram_phone: str (your phone number)
        - telegram_session: str (session file name, optional)
    """

    bot_username: str = ""  # Override in subclass

    @property
    def signup_url(self) -> str:
        return f"https://t.me/{self.bot_username.lstrip('@')}"

    async def _get_client(self):
        """Create and connect a Telethon client."""
        try:
            from telethon import TelegramClient
        except ImportError:
            raise RuntimeError(
                "telethon not installed. Run: pip install telethon"
            )

        api_id = self.config.get("telegram_api_id")
        api_hash = self.config.get("telegram_api_hash")
        phone = self.config.get("telegram_phone")
        session = self.config.get("telegram_session", f"session_{self.provider_name}")

        if not all([api_id, api_hash, phone]):
            raise ValueError(
                "telegram_api_id, telegram_api_hash, and telegram_phone "
                "are required in config"
            )

        client = TelegramClient(session, api_id, api_hash)
        await client.start(phone=phone)
        return client

    async def _do_signup(self, page) -> CardResult:
        """
        Override the browser-based signup with Telegram interaction.
        The `page` argument is ignored — we use Telethon instead.
        """
        card = CardResult(provider=self.provider_name, signup_url=self.signup_url)

        try:
            client = await self._get_client()
            card = await self._parse_bot_flow(client, card)
            await client.disconnect()
        except Exception as e:
            card.status = SignupStatus.FAILED
            card.error = str(e)

        return card

    async def _parse_bot_flow(
        self, client, card: CardResult
    ) -> CardResult:
        """
        Override this method with the provider-specific bot interaction.

        Example flow:
            1. Send /start to bot
            2. Parse menu buttons
            3. Select "Get Card"
            4. Choose card type
            5. Extract deposit address
        """
        raise NotImplementedError("Subclass must implement _parse_bot_flow")

    async def _send_and_wait(
        self, client, bot: str, message: str, timeout: int = 30
    ) -> Optional[str]:
        """
        Send a message to a bot and wait for its reply.
        Returns the reply text, or None on timeout.
        """
        from telethon import events

        response_text = None
        got_response = asyncio.Event()

        @client.on(events.NewMessage(from_users=bot))
        async def handler(event):
            nonlocal response_text
            response_text = event.message.text
            got_response.set()

        await client.send_message(bot, message)

        try:
            await asyncio.wait_for(got_response.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout waiting for reply from {bot}")

        client.remove_event_handler(handler)
        return response_text

    async def _click_inline_button(
        self, client, bot: str, button_text: str, timeout: int = 15
    ) -> Optional[str]:
        """
        Click an inline keyboard button by its text label and
        wait for the bot's next message.
        """
        from telethon.tl.types import ReplyInlineMarkup

        # Get the most recent message from the bot
        messages = await client.get_messages(bot, limit=1)
        if not messages:
            return None

        msg = messages[0]
        if not msg.reply_markup or not isinstance(msg.reply_markup, ReplyInlineMarkup):
            self.logger.warning("No inline keyboard found")
            return None

        # Find and click the button
        for row in msg.reply_markup.rows:
            for button in row.buttons:
                if button_text.lower() in button.text.lower():
                    await msg.click(data=button.data)
                    await asyncio.sleep(2)

                    # Get the bot's response
                    new_messages = await client.get_messages(bot, limit=1)
                    if new_messages and new_messages[0].id != msg.id:
                        return new_messages[0].text
                    return None

        self.logger.warning(f"Button '{button_text}' not found")
        return None

    async def _do_health_check(self, page, card: CardResult) -> bool:
        """Health check via Telegram — send status command to bot."""
        try:
            client = await self._get_client()
            reply = await self._send_and_wait(
                client, self.bot_username, "/status", timeout=15
            )
            await client.disconnect()

            if reply:
                lower = reply.lower()
                if any(w in lower for w in ["frozen", "disabled", "blocked"]):
                    return False
                if any(w in lower for w in ["active", "valid", "balance"]):
                    return True

            return True  # Assume active if unclear

        except Exception as e:
            self.logger.error(f"Telegram health check failed: {e}")
            return False

    # Override browser methods to no-op (we don't use a browser)
    async def _launch_browser(self):
        pass

    async def _new_context(self):
        pass

    async def _close(self):
        pass

    async def signup(self) -> CardResult:
        """Direct signup without browser scaffolding."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self.logger.info(
                    f"Telegram signup attempt {attempt}/{self.MAX_RETRIES} "
                    f"for {self.provider_name}"
                )
                card = await self._do_signup(page=None)
                if card.status != SignupStatus.FAILED:
                    return card
            except Exception as e:
                self.logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))

        return CardResult(
            provider=self.provider_name,
            status=SignupStatus.FAILED,
            error="All Telegram signup attempts failed",
        )


# ── Example: ZeroID CC bot agent ──────────────────────────────────────

class ZeroIDAgent(TelegramBotAgent):
    """
    ZeroID CC — Telegram-bot-based no-KYC card issuer.
    Possibly a Zypto reseller. Offers both Visa and Mastercard.
    """

    bot_username = "@ZeroID_bot"  # UPDATE with actual bot username

    @property
    def provider_name(self) -> str:
        return "zeroid_cc"

    async def _parse_bot_flow(self, client, card: CardResult) -> CardResult:
        """
        ZeroID bot flow (approximate — update based on actual bot):
        1. /start → Welcome message with menu
        2. "Get Card" button → Card type selection
        3. Select Visa/Mastercard → Denomination options
        4. Select amount → Deposit address shown
        """
        bot = self.bot_username

        # Step 1: Start the bot
        reply = await self._send_and_wait(client, bot, "/start")
        self.logger.info(f"Bot welcome: {reply[:100] if reply else 'No reply'}")

        if not reply:
            card.status = SignupStatus.FAILED
            card.error = "Bot did not respond to /start"
            return card

        # Step 2: Click "Get Card" or similar
        reply = await self._click_inline_button(client, bot, "card")
        self.logger.info(f"After card selection: {reply[:100] if reply else 'N/A'}")

        # Step 3: Select Visa
        reply = await self._click_inline_button(client, bot, "visa")
        if reply:
            card.network = CardNetwork.VISA
        else:
            # Try Mastercard
            reply = await self._click_inline_button(client, bot, "master")
            if reply:
                card.network = CardNetwork.MASTERCARD

        # Step 4: Look for deposit address in the reply
        if reply:
            # Common patterns: BTC/LTC/USDT addresses
            addr_patterns = [
                r"([13][a-km-zA-HJ-NP-Z1-9]{25,34})",     # BTC legacy
                r"(bc1[a-zA-HJ-NP-Z0-9]{39,59})",          # BTC bech32
                r"(0x[a-fA-F0-9]{40})",                      # ETH/USDT ERC20
                r"(T[a-zA-Z0-9]{33})",                       # USDT TRC20
                r"([LM][a-km-zA-HJ-NP-Z1-9]{26,33})",      # LTC
            ]
            for pattern in addr_patterns:
                match = re.search(pattern, reply)
                if match:
                    card.deposit_address = match.group(1)
                    card.status = SignupStatus.AWAITING_DEPOSIT
                    self.logger.info(
                        f"Found deposit address: "
                        f"{card.deposit_address[:10]}..."
                    )
                    break

            # Try to extract amount
            amount_match = re.search(
                r"([\d.]+)\s*(BTC|LTC|USDT|ETH|USDC)", reply, re.IGNORECASE
            )
            if amount_match:
                card.deposit_amount = float(amount_match.group(1))
                card.deposit_currency = amount_match.group(2).upper()

        if not card.deposit_address:
            card.status = SignupStatus.FAILED
            card.error = "Could not extract deposit address from bot"

        return card
