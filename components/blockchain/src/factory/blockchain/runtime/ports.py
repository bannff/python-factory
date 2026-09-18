"""Protocol interfaces for the blockchain brick.

LedgerPort defines the contract for all ledger backends:
- MockLedger (in-memory, default)
- Neo4jLedgerAdapter (graph-backed, production)
"""

from __future__ import annotations

from typing import Any, Protocol

from .models import Block, Bounty, ChainInfo, Transaction, Wallet


class LedgerPort(Protocol):
    """Abstract ledger interface for the agent economy."""

    def create_wallet(self, owner_id: str, initial_balance: float = 0) -> Wallet:
        """Create a new wallet for an agent/user."""
        ...

    def get_wallet(self, wallet_id: str) -> Wallet | None:
        """Get wallet by ID."""
        ...

    def transfer(
        self, from_wallet: str, to_wallet: str, amount: float, memo: str = "",
    ) -> Transaction:
        """Transfer tokens between wallets."""
        ...

    def get_balance(self, wallet_id: str) -> float:
        """Get current balance for a wallet."""
        ...

    def get_transactions(
        self, wallet_id: str | None = None, limit: int = 50,
    ) -> list[Transaction]:
        """List transactions, optionally filtered by wallet."""
        ...

    def mint(self, to_wallet: str, amount: float, memo: str = "") -> Transaction:
        """Mint new tokens into a wallet (treasury operation)."""
        ...

    def post_bounty(
        self, poster_wallet: str, amount: float,
        description: str = "", criteria: dict | None = None,
    ) -> Bounty:
        """Post a bounty with escrowed tokens."""
        ...

    def claim_bounty(self, bounty_id: str, claimer_wallet: str) -> Transaction:
        """Claim a bounty and release escrowed tokens."""
        ...

    def get_bounty(self, bounty_id: str) -> Bounty | None:
        """Get bounty by ID."""
        ...

    def cancel_bounty(self, bounty_id: str) -> Transaction:
        """Cancel an open bounty and return escrowed tokens to poster."""
        ...

    def list_bounties(
        self, status: str | None = None, limit: int = 50,
    ) -> list[Bounty]:
        """List bounties, optionally filtered by status."""
        ...

    def get_block(self, height: int) -> Block | None:
        """Get block by height."""
        ...

    def get_chain_info(self) -> ChainInfo:
        """Get summary of chain state."""
        ...

    def verify_chain(self) -> dict[str, Any]:
        """Walk the chain and verify hash integrity."""
        ...

    def reconcile(self, wallet_id: str) -> dict[str, Any]:
        """Recompute wallet balance from transaction history."""
        ...

    def health_check(self) -> dict[str, Any]:
        """Readiness probe."""
        ...
