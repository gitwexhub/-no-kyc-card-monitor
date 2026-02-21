"""
Crypto payment helpers.

Handles sending deposits to card provider addresses.
Supports multiple chains via a plugin approach.

IMPORTANT: This module deals with real money. Use small amounts for testing.
Always verify addresses before sending.

Requires (depending on chain):
    pip install web3          # EVM chains (ETH, USDT-ERC20, USDC, etc.)
    pip install bitcoinlib    # BTC
"""

import asyncio
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
    """Abstract base for chain-specific senders."""

    @abstractmethod
    async def send(
        self, to_address: str, amount: float, currency: str
    ) -> PaymentResult:
        ...

    @abstractmethod
    async def get_balance(self) -> float:
        ...


class EVMSender(ChainSender):
    """
    Send payments on EVM chains (Ethereum, Polygon, Arbitrum, Base, etc.)
    Supports native ETH and ERC-20 tokens (USDT, USDC, DAI).
    """

    # Common ERC-20 contract addresses (Ethereum mainnet)
    TOKEN_CONTRACTS = {
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    }

    # Minimal ERC-20 ABI for transfer
    ERC20_ABI = [
        {
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function",
        },
        {
            "inputs": [{"name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function",
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function",
        },
    ]

    def __init__(self, rpc_url: str, private_key: str):
        try:
            from web3 import Web3
        except ImportError:
            raise RuntimeError("web3 not installed. Run: pip install web3")

        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.account = self.w3.eth.account.from_key(private_key)
        self.address = self.account.address
        logger.info(f"EVM sender initialized: {self.address}")

    async def send(
        self, to_address: str, amount: float, currency: str = "ETH"
    ) -> PaymentResult:
        """Send ETH or ERC-20 token."""
        try:
            currency = currency.upper()

            if currency in ("ETH", "MATIC", "BNB"):
                return await self._send_native(to_address, amount)
            elif currency in self.TOKEN_CONTRACTS:
                return await self._send_erc20(to_address, amount, currency)
            else:
                return PaymentResult(
                    success=False, error=f"Unsupported currency: {currency}"
                )

        except Exception as e:
            logger.error(f"EVM send failed: {e}")
            return PaymentResult(success=False, error=str(e))

    async def _send_native(self, to: str, amount: float) -> PaymentResult:
        """Send native chain token (ETH, MATIC, etc.)."""
        from web3 import Web3

        value = Web3.to_wei(amount, "ether")
        nonce = self.w3.eth.get_transaction_count(self.address)
        gas_price = self.w3.eth.gas_price

        tx = {
            "nonce": nonce,
            "to": Web3.to_checksum_address(to),
            "value": value,
            "gas": 21000,
            "gasPrice": gas_price,
        }

        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

        logger.info(f"Native TX sent: {tx_hash.hex()}")
        return PaymentResult(
            success=True,
            tx_hash=tx_hash.hex(),
            chain="evm",
            amount=amount,
            currency="ETH",
        )

    async def _send_erc20(
        self, to: str, amount: float, token: str
    ) -> PaymentResult:
        """Send an ERC-20 token."""
        from web3 import Web3

        contract_addr = self.TOKEN_CONTRACTS[token]
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(contract_addr),
            abi=self.ERC20_ABI,
        )

        decimals = contract.functions.decimals().call()
        token_amount = int(amount * (10**decimals))

        nonce = self.w3.eth.get_transaction_count(self.address)
        tx = contract.functions.transfer(
            Web3.to_checksum_address(to), token_amount
        ).build_transaction(
            {
                "from": self.address,
                "nonce": nonce,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

        logger.info(f"ERC-20 TX sent ({token}): {tx_hash.hex()}")
        return PaymentResult(
            success=True,
            tx_hash=tx_hash.hex(),
            chain="evm",
            amount=amount,
            currency=token,
        )

    async def get_balance(self) -> float:
        from web3 import Web3
        bal = self.w3.eth.get_balance(self.address)
        return float(Web3.from_wei(bal, "ether"))


class PaymentManager:
    """
    High-level payment manager. Routes payments to the correct
    chain sender based on the deposit details from a CardResult.
    """

    def __init__(self, config: dict):
        """
        Config example:
        {
            "evm": {
                "rpc_url": "https://eth-mainnet.g.alchemy.com/v2/...",
                "private_key": "0x..."
            }
        }
        """
        self._senders: dict[str, ChainSender] = {}

        if "evm" in config:
            self._senders["evm"] = EVMSender(
                rpc_url=config["evm"]["rpc_url"],
                private_key=config["evm"]["private_key"],
            )

        # Add more chain senders here (BTC, LTC, TRC20, etc.)

    def _resolve_chain(self, deposit_chain: str, deposit_address: str) -> Optional[str]:
        """Guess which sender to use from the chain/address."""
        chain = (deposit_chain or "").lower()

        # EVM chains
        if chain in ("eth", "ethereum", "erc20", "usdt-erc20", "usdc", "polygon", "arbitrum", "base"):
            return "evm"
        if deposit_address and deposit_address.startswith("0x") and len(deposit_address) == 42:
            return "evm"

        # BTC
        if chain in ("btc", "bitcoin"):
            return "btc"
        if deposit_address and (
            deposit_address.startswith(("1", "3", "bc1"))
        ):
            return "btc"

        # TRC20 (Tron)
        if chain in ("trc20", "tron", "usdt-trc20"):
            return "trc20"
        if deposit_address and deposit_address.startswith("T"):
            return "trc20"

        return None

    async def send_deposit(
        self,
        to_address: str,
        amount: float,
        currency: str,
        chain: str = None,
    ) -> PaymentResult:
        """Send a deposit to a card provider's address."""
        sender_key = self._resolve_chain(chain, to_address)

        if not sender_key:
            return PaymentResult(
                success=False,
                error=f"Cannot resolve chain for address {to_address[:20]}...",
            )

        sender = self._senders.get(sender_key)
        if not sender:
            return PaymentResult(
                success=False,
                error=f"No sender configured for chain '{sender_key}'. "
                       f"Add it to PaymentManager config.",
            )

        logger.info(
            f"Sending {amount} {currency} to {to_address[:16]}... "
            f"via {sender_key}"
        )
        return await sender.send(to_address, amount, currency)
