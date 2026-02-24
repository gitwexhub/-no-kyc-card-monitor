#!/bin/bash
# Run the daily monitor manually
# Usage: ./run_monitor.sh [--telegram]

cd /Users/wexler/-no-kyc-card-monitor
/usr/bin/python3 daily_monitor.py "$@"

echo ""
echo "Results saved to: output/latest.json"
