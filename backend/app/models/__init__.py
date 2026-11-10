"""Central registration point for all SQLAlchemy models."""

from backend.app.models.account import Account
from backend.app.models.asset import Asset
from backend.app.models.holding import Holding
from backend.app.models.portfolio import Portfolio
from backend.app.models.scheduled_transaction import ScheduledTransaction
from backend.app.models.transaction import Transaction
from backend.app.models.user import User

__all__ = [
    "Account",
    "Asset",
    "Holding",
    "Portfolio",
    "ScheduledTransaction",
    "Transaction",
    "User",
]