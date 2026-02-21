# No-KYC Card Signup Agent

Automated signup and monitoring agent for no-KYC crypto card providers. Extends the [no-kyc-card-monitor](https://github.com/gitwexhub/-no-kyc-card-monitor) scanner with active signup capabilities.

## Architecture

```
card_agent.py                 # CLI orchestrator
├── agents/
│   ├── base_agent.py         # Abstract base (Playwright browser automation)
│   ├── registry.py           # Auto-discovery of provider agents
│   ├── telegram_agent.py     # Base for Telegram-bot providers + ZeroID example
│   └── ezzocard_agent.py     # Reference web-based agent implementation
├── config/
│   ├── providers.py          # Provider database (URLs, networks, limits, fees)
│   └── agent_config.json     # Runtime config (proxies, keys, etc.)
├── crypto/
│   └── __init__.py           # Payment manager (EVM, extensible to BTC/TRC20)
└── storage/
    └── __init__.py           # AES-256 encrypted card storage
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements-agent.txt
playwright install chromium

# Copy and edit config
cp config/agent_config.example.json config/agent_config.json

# List available providers
python card_agent.py providers

# Sign up for a specific provider
python card_agent.py signup ezzocard

# Sign up for all active providers
python card_agent.py signup --all

# Check if your cards are still active
python card_agent.py health-check

# List all stored cards
python card_agent.py list
```

## Adding a New Provider Agent

1. Create `agents/yourprovider_agent.py`
2. Inherit from `BaseCardAgent` (web) or `TelegramBotAgent` (Telegram)
3. Implement the required methods:

```python
from agents.base_agent import BaseCardAgent, CardResult, SignupStatus, CardNetwork

class YourProviderAgent(BaseCardAgent):
    @property
    def provider_name(self) -> str:
        return "yourprovider"

    @property
    def signup_url(self) -> str:
        return "https://yourprovider.com/signup"

    async def _do_signup(self, page) -> CardResult:
        card = CardResult(provider=self.provider_name)
        # ... your signup automation here ...
        return card

    async def _do_health_check(self, page, card) -> bool:
        # ... check if card is still active ...
        return True
```

4. Add provider config to `config/providers.py`
5. The agent is auto-discovered — no registration needed

## Pipeline Flow

```
Scanner detects provider → Agent signs up → Deposit sent → Card issued → Health monitored
        ↓                       ↓                ↓              ↓              ↓
   (existing repo)      (base_agent.py)    (crypto/)     (storage/)    (health_check)
```

## Security Notes

- Card details are stored AES-256-GCM encrypted — set `CARD_STORE_KEY` env var
- **Never commit** `agent_config.json` (it's in `.gitignore`)
- Private keys for crypto wallets should use env vars, not config files
- Use residential proxies to avoid IP-based blocking
- The `_random_delay()` helper adds human-like timing between actions

## Provider Coverage

| Provider | Type | Agent Status | Networks |
|----------|------|-------------|----------|
| Ezzocard | Web | ✅ Reference impl | Visa, MC |
| ZeroID CC | Telegram | ✅ Reference impl | Visa, MC |
| SolCard | Web | 🔲 Template only | MC |
| BingCard | Web | 🔲 Template only | Visa, MC |
| Laso Finance | Web | 🔲 Template only | Visa |
| PSTnet | Web | 🔲 Template only | Visa, MC |
| Trocador | Web | 🔲 Template only | Visa, MC |
| *12 more...* | Various | 🔲 Template only | Various |

## Known Risks

Many "no-KYC" providers retroactively freeze accounts and demand KYC when AML flags trigger. The health-check system monitors for this. See the research notes in `config/providers.py` for per-provider risk assessments.
