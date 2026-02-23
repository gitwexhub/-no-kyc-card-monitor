#!/bin/bash
# setup_agent.sh — Run this from the root of your -no-kyc-card-monitor repo
# It moves files into the correct package structure.
#
# Usage:
#   cd -no-kyc-card-monitor
#   bash setup_agent.sh

set -e
echo "=== No-KYC Card Agent — Setup ==="
echo ""

# Create package directories
echo "Creating directories..."
mkdir -p agents config crypto storage

# Move agent files
echo "Moving agent files..."
[ -f base_agent.py ] && mv base_agent.py agents/
[ -f bin_lookup.py ] && mv bin_lookup.py agents/
[ -f ezzocard_agent.py ] && mv ezzocard_agent.py agents/
[ -f registry.py ] && mv registry.py agents/
[ -f telegram_agent.py ] && mv telegram_agent.py agents/

# Move config files
echo "Moving config files..."
[ -f providers.py ] && mv providers.py config/
[ -f agent_config.example.json ] && mv agent_config.example.json config/
# Handle alternate name
[ -f agent_config_example.json ] && mv agent_config_example.json config/agent_config.example.json

# Handle __init__.py files
# The uploaded __init__.py is the storage module (176 lines)
echo "Setting up __init__.py files..."
if [ -f __init__.py ]; then
    cp __init__.py storage/__init__.py
    rm __init__.py
fi

# Create agents/__init__.py
cat > agents/__init__.py << 'PYEOF'
from agents.base_agent import BaseCardAgent
from agents.registry import AgentRegistry

__all__ = ["BaseCardAgent", "AgentRegistry"]
PYEOF

# Create config/__init__.py
touch config/__init__.py

# Check if crypto/__init__.py exists, if not create a placeholder
if [ ! -f crypto/__init__.py ]; then
    echo "NOTE: crypto/__init__.py (payment module) needs to be added."
    echo "      Creating placeholder..."
    cat > crypto/__init__.py << 'PYEOF'
"""
Crypto payment helpers — placeholder.
Replace this file with the full crypto/__init__.py from Claude.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class PaymentResult:
    success: bool
    tx_hash: Optional[str] = None
    chain: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    error: Optional[str] = None

class PaymentManager:
    def __init__(self, config: dict):
        self._senders = {}

    async def send_deposit(self, to_address, amount, currency, chain=None):
        return PaymentResult(success=False, error="Payment module not configured")
PYEOF
fi

# Verify structure
echo ""
echo "=== Final structure ==="
echo ""
find agents config crypto storage -type f 2>/dev/null | sort
echo ""
ls -la card_agent.py test_dry_run.py requirements-agent.txt README-agent.md 2>/dev/null
echo ""

# Check for missing files
MISSING=0
for f in agents/base_agent.py agents/bin_lookup.py agents/ezzocard_agent.py \
         agents/registry.py agents/telegram_agent.py config/providers.py \
         storage/__init__.py card_agent.py test_dry_run.py; do
    if [ ! -f "$f" ]; then
        echo "WARNING: Missing $f"
        MISSING=1
    fi
done

if [ $MISSING -eq 0 ]; then
    echo "✅ All files in place!"
    echo ""
    echo "Next steps:"
    echo "  1. pip install playwright cryptography"
    echo "  2. playwright install chromium"
    echo "  3. python test_dry_run.py"
    echo ""
    echo "To commit:"
    echo "  git add ."
    echo "  git commit -m 'Organize agent files into package structure'"
    echo "  git push origin main"
else
    echo ""
    echo "⚠️  Some files are missing. Download them from Claude and re-run."
fi
