"""
Crypto payment helpers.

Handles sending deposits to card provider addresses.
Supports EVM chains (ETH, USDT, USDC, etc.) with extensible design.

IMPORTANT: This module deals with real money. Use small amounts for testing.
Always verify addresses before sending.

Requires: pip install web3
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("crypto")


@dataclass
class PaymentResult:
    success: bool
    tx_hash: Optional[str] = None
    chain: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    error: Optional[str] = None


class ChainSender(ABC):
    """Abstract base for chain-specific payment senders."""

    @abstractmethod
    async def send(self, to_address: str, amount: float, currency: str) -> PaymentResult:
        ...

    @abstractmethod
    async def get_balance(self) -> float:
        ...


class EVMSender(ChainSender):
    """Send payments on EVM chains (ETH, Polygon, Arbitrum, Base, etc.)."""

    TOKEN_CONTRACTS = {
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "DAI":  "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    }

    ERC20_ABI = [
        {"inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
         "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
        {"inputs": [{"name": "account", "type": "address"}],
         "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
        {"inputs": [], "name": "decimals",
         "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    ]

    def __init__(self, rpc_url: str, private_key: str):
        from web3 import Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.account = self.w3.eth.account.from_key(private_key)
        self.address = self.account.address

    async def send(self, to_address: str, amount: float, currency: str = "ETH") -> PaymentResult:
        try:
            currency = currency.upper()
            if currency in ("ETH", "MATIC", "BNB"):
                return await self._send_native(to_address, amount)
            elif currency in self.TOKEN_CONTRACTS:
                return await self._send_erc20(to_address, amount, currency)
            else:
                return PaymentResult(success=False, error=f"Unsupported: {currency}")
        except Exception as e:
            return PaymentResult(success=False, error=str(e))

    async def _send_native(self, to: str, amount: float) -> PaymentResult:
        from web3 import Web3
        tx = {
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "to": Web3.to_checksum_address(to),
            "value": Web3.to_wei(amount, "ether"),
            "gas": 21000,
            "gasPrice": self.w3.eth.gas_price,
        }
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return PaymentResult(success=True, tx_hash=tx_hash.hex(), chain="evm", amount=amount, currency="ETH")

    async def _send_erc20(self, to: str, amount: float, token: str) -> PaymentResult:
        from web3 import Web3
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.TOKEN_CONTRACTS[token]),
            abi=self.ERC20_ABI,
        )
        decimals = contract.functions.decimals().call()
        tx = contract.functions.transfer(
            Web3.to_checksum_address(to), int(amount * (10 ** decimals))
        ).build_transaction({
            "from": self.address,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return PaymentResult(success=True, tx_hash=tx_hash.hex(), chain="evm", amount=amount, currency=token)

    async def get_balance(self) -> float:
        from web3 import Web3
        return float(Web3.from_wei(self.w3.eth.get_balance(self.address), "ether"))


class PaymentManager:
    """Routes payments to the correct chain sender."""

    def __init__(self, config: dict):
        self._senders: dict[str, ChainSender] = {}
        if "evm" in config:
            self._senders["evm"] = EVMSender(
                rpc_url=config["evm"]["rpc_url"],
                private_key=config["evm"]["private_key"],
            )

    def _resolve_chain(self, chain: str, address: str) -> Optional[str]:
        chain = (chain or "").lower()
        if chain in ("eth", "ethereum", "erc20", "usdt_erc20", "usdc", "polygon", "arbitrum"):
            return "evm"
        if address and address.startswith("0x") and len(address) == 42:
            return "evm"
        if chain in ("btc", "bitcoin") or (address and address.startswith(("1", "3", "bc1"))):
            return "btc"
        if chain in ("trc20", "usdt_trc20") or (address and address.startswith("T")):
            return "trc20"
        return None

    async def send_deposit(self, to_address: str, amount: float, currency: str, chain: str = None) -> PaymentResult:
        sender_key = self._resolve_chain(chain, to_address)
        if not sender_key:
            return PaymentResult(success=False, error=f"Cannot resolve chain for {to_address[:20]}")
        sender = self._senders.get(sender_key)
        if not sender:
            return PaymentResult(success=False, error=f"No sender for chain '{sender_key}'")
        return await sender.send(to_address, amount, currency)
