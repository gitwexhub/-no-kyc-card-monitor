# No-KYC Card Monitor

Daily scanner and automated signup agent for no-KYC cryptocurrency prepaid card providers. Monitors card availability, prices, and provider status across multiple services.

## Features

- **Daily Monitoring**: Automated scanning of 15+ no-KYC card providers
- **Price Tracking**: Captures card denominations, prices, and stock availability
- **Provider Discovery**: Searches for new no-KYC card providers
- **Automated Signup**: Browser automation for card purchase flows (Ezzocard implemented)
- **Telegram Notifications**: Optional alerts for monitoring results
- **Encrypted Storage**: AES-256 encrypted storage for card details

## Project Structure

```
├── daily_monitor.py          # Daily monitoring script (main entry point)
├── card_agent.py             # CLI for signup operations
├── run_monitor.sh            # Manual run script
├── agents/
│   ├── base_agent.py         # Abstract base (Playwright browser automation)
│   ├── ezzocard_agent.py     # Ezzocard provider implementation
│   ├── bin_lookup.py         # BIN/IIN lookup for card identification
│   ├── registry.py           # Auto-discovery of provider agents
│   └── telegram_agent.py     # Base for Telegram-bot providers
├── config/
│   └── providers.py          # Provider database (URLs, networks, fees)
├── crypto/
│   └── __init__.py           # Payment manager (EVM chains)
├── storage/
│   └── __init__.py           # Encrypted card storage
└── output/
    └── latest.json           # Most recent scan results
```

## Installation

```bash
# Clone the repository
git clone https://github.com/gitwexhub/-no-kyc-card-monitor.git
cd -no-kyc-card-monitor

# Install dependencies
pip install playwright cryptography httpx

# Install browser
playwright install chromium
```

## Usage

### Daily Monitor

Run the daily monitor to scan all providers:

```bash
# Run manually
./run_monitor.sh

# Or directly with Python
python daily_monitor.py

# With Telegram notifications
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python daily_monitor.py --telegram
```

Results are saved to `output/latest.json`.

### Scheduled Execution (macOS)

The monitor can be scheduled to run daily at 8:00 AM:

```bash
# Load the schedule
launchctl load ~/Library/LaunchAgents/com.nokyc.cardmonitor.plist

# Unload the schedule
launchctl unload ~/Library/LaunchAgents/com.nokyc.cardmonitor.plist

# Check status
launchctl list | grep nokyc
```

### Card Agent CLI

```bash
# List available providers
python card_agent.py providers

# Sign up for a specific provider (monitor only by default)
python card_agent.py signup ezzocard

# Check card health
python card_agent.py health-check

# List stored cards
python card_agent.py list
```

## Monitored Providers

| Provider | URL | Status | Networks |
|----------|-----|--------|----------|
| Ezzocard | ezzocard.finance | ✅ Full agent | Visa, MC |
| LinkPay | linkpay.to | ✅ Operational | Visa, MC |
| PayWide | paywide.io | ✅ Operational | Visa, MC |
| XKard | xkard.io | ✅ Operational | Visa |
| Zypto | zypto.com | ✅ Operational | MC |
| PlasBit | plasbit.com | 🔧 Maintenance | Visa, MC |
| Rewarble | rewarble.com | 🔧 Maintenance | MC |
| SolCard | solcard.io | ❓ Unclear | MC |
| FotonCard | fotoncard.com | ❓ Unclear | Visa, MC |
| PSTnet | pst.net | ❓ Unclear | Visa, MC |
| Laso Finance | laso.finance | ⏸️ Coming Soon | Visa |
| KripiCard | kripicard.com | ⏸️ Waitlist | Visa |
| Trocador | trocador.app | ❓ Unclear | Visa, MC |
| ZeroID CC | Telegram | 📱 Telegram-based | Visa, MC |
| BingCard | bingcard.io | ❌ Offline | Visa, MC |

## Output Format

The monitor outputs JSON with provider status and card catalog:

```json
{
  "run_date": "2026-02-24T01:57:02",
  "providers": [
    {
      "provider": "ezzocard",
      "status": "awaiting_deposit",
      "catalog": [
        {
          "denomination": "50",
          "currency": "USD",
          "price": "74.99",
          "color": "violet",
          "network": "visa",
          "in_stock": true
        }
      ],
      "total_products": 54,
      "in_stock": 48,
      "target_price": "74.99"
    }
  ],
  "new_providers": []
}
```

## Adding a New Provider

1. Create `agents/yourprovider_agent.py`
2. Inherit from `BaseCardAgent`
3. Implement required methods:

```python
from agents.base_agent import BaseCardAgent, CardResult

class YourProviderAgent(BaseCardAgent):
    @property
    def provider_name(self) -> str:
        return "yourprovider"

    @property
    def signup_url(self) -> str:
        return "https://yourprovider.com"

    async def _do_signup(self, page) -> CardResult:
        # Your automation logic
        pass

    async def _do_health_check(self, page, card) -> bool:
        return True
```

4. Add provider to `config/providers.py`

## Security Notes

- Card details are AES-256-GCM encrypted (set `CARD_STORE_KEY` env var)
- Never commit `agent_config.json` (contains sensitive keys)
- Use residential proxies to avoid IP blocking
- The agents include random delays for human-like behavior

## Known Risks

Many "no-KYC" providers may retroactively freeze accounts and demand KYC when AML flags trigger. The health-check system monitors for this. See `config/providers.py` for per-provider risk notes.

## License

MIT
