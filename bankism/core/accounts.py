"""Account and Transaction data models for Bankism Core Banking."""

from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import uuid


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    RESTRICTED = "RESTRICTED"


class CardStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    BLOCKED = "BLOCKED"


class Beneficiary(BaseModel):
    beneficiary_id: str
    name: str
    account_id: str
    bank_routing: str = "BKSMUS33"
    is_verified: bool = True
    max_limit: float = 5000.00


class TransactionRecord(BaseModel):
    tx_id: str = Field(default_factory=lambda: f"TXN-{uuid.uuid4().hex[:8].upper()}")
    from_account: str
    to_account: str
    amount: float
    currency: str = "USD"
    status: str = "COMPLETED"
    description: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    step_up_approved: bool = False


class BankAccount(BaseModel):
    account_id: str
    owner_name: str
    email: str
    balance: float
    currency: str = "USD"
    status: AccountStatus = AccountStatus.ACTIVE
    card_number_masked: str = "•••• •••• •••• 4242"
    card_status: CardStatus = CardStatus.ACTIVE
    security_pin: str = "1234"
    beneficiaries: List[Beneficiary] = Field(default_factory=list)
    daily_transferred_amount: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
