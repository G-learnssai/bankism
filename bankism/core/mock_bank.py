"""Core Banking engine and double-entry ledger simulation."""

from typing import Dict, List, Optional, Tuple
import threading
from datetime import datetime, timezone
from bankism.core.accounts import BankAccount, AccountStatus, CardStatus, Beneficiary, TransactionRecord
from bankism.config import config


class BankingResult:
    def __init__(self, success: bool, message: str, data: Optional[dict] = None, error_code: Optional[str] = None):
        self.success = success
        self.message = message
        self.data = data or {}
        self.error_code = error_code

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "error_code": self.error_code,
        }


class CoreBankingService:
    def __init__(self):
        self._lock = threading.RLock()
        self.accounts: Dict[str, BankAccount] = {}
        self.transactions: List[TransactionRecord] = []
        self.reset_to_default()

    def reset_to_default(self):
        with self._lock:
            self.accounts.clear()
            self.transactions.clear()

            # Seed default accounts
            alice_beneficiaries = [
                Beneficiary(beneficiary_id="BEN-BOB", name="Bob Jones", account_id="ACC-BOB-2002", max_limit=3000.0),
                Beneficiary(beneficiary_id="BEN-CHARLIE", name="Charlie Davis", account_id="ACC-CHARLIE-3003", max_limit=1500.0),
            ]

            self.accounts["ACC-ALICE-1001"] = BankAccount(
                account_id="ACC-ALICE-1001",
                owner_name="Alice Smith",
                email="alice.smith@securebank.example",
                balance=12500.00,
                status=AccountStatus.ACTIVE,
                card_number_masked="•••• •••• •••• 4242",
                card_status=CardStatus.ACTIVE,
                security_pin="1234",
                beneficiaries=alice_beneficiaries,
            )

            self.accounts["ACC-BOB-2002"] = BankAccount(
                account_id="ACC-BOB-2002",
                owner_name="Bob Jones",
                email="bob.jones@securebank.example",
                balance=3400.00,
                status=AccountStatus.ACTIVE,
                card_number_masked="•••• •••• •••• 1188",
                card_status=CardStatus.ACTIVE,
                security_pin="4321",
                beneficiaries=[],
            )

            self.accounts["ACC-CHARLIE-3003"] = BankAccount(
                account_id="ACC-CHARLIE-3003",
                owner_name="Charlie Davis",
                email="charlie.d@securebank.example",
                balance=850.00,
                status=AccountStatus.ACTIVE,
                card_number_masked="•••• •••• •••• 9921",
                card_status=CardStatus.ACTIVE,
                security_pin="2580",
                beneficiaries=[],
            )

            self.accounts["ACC-MALLORY-6666"] = BankAccount(
                account_id="ACC-MALLORY-6666",
                owner_name="Mallory Hacker",
                email="mallory@darkweb.example",
                balance=100.00,
                status=AccountStatus.ACTIVE,
                card_number_masked="•••• •••• •••• 6666",
                card_status=CardStatus.ACTIVE,
                security_pin="6666",
                beneficiaries=[],
            )

    def get_account(self, account_id: str) -> Optional[BankAccount]:
        with self._lock:
            return self.accounts.get(account_id)

    def verify_pin(self, account_id: str, pin: str) -> bool:
        with self._lock:
            account = self.accounts.get(account_id)
            if not account or not pin:
                return False
            return str(account.security_pin).strip() == str(pin).strip()

    def set_pin(self, account_id: str, new_pin: str, old_pin: Optional[str] = None) -> BankingResult:
        with self._lock:
            account = self.accounts.get(account_id)
            if not account:
                return BankingResult(False, f"Account '{account_id}' not found.", error_code="ACCOUNT_NOT_FOUND")
            
            # If a PIN is already set, old PIN must be provided and correct
            if account.security_pin:
                if not old_pin or str(old_pin).strip() != str(account.security_pin).strip():
                    return BankingResult(False, "Current PIN is incorrect or missing. You must provide the correct current PIN to change it.", error_code="INVALID_OLD_PIN")

            cleaned = str(new_pin).strip()
            if not cleaned.isdigit() or len(cleaned) < 4 or len(cleaned) > 6:
                return BankingResult(False, "Security PIN must be a 4 to 6 digit numeric code.", error_code="INVALID_PIN")
            account.security_pin = cleaned
            return BankingResult(True, f"Security PIN updated successfully for {account.owner_name}.", data={"account_id": account_id})

    def get_all_accounts(self) -> List[BankAccount]:
        with self._lock:
            return list(self.accounts.values())

    def get_balance(self, account_id: str) -> BankingResult:
        with self._lock:
            account = self.accounts.get(account_id)
            if not account:
                return BankingResult(False, f"Account '{account_id}' not found.", error_code="ACCOUNT_NOT_FOUND")
            return BankingResult(
                True,
                f"Balance for {account.owner_name} ({account.account_id}) is ${account.balance:,.2f} {account.currency}.",
                data={
                    "account_id": account.account_id,
                    "owner_name": account.owner_name,
                    "balance": account.balance,
                    "currency": account.currency,
                    "status": account.status.value,
                    "card_status": account.card_status.value,
                },
            )

    def transfer_funds(
        self,
        from_account_id: str,
        to_account_id: str,
        amount: float,
        description: str = "P2P Transfer",
        step_up_token_verified: bool = False,
    ) -> BankingResult:
        with self._lock:
            if amount <= 0:
                return BankingResult(False, "Transfer amount must be strictly greater than $0.00.", error_code="INVALID_AMOUNT")

            if amount > config.MAX_DAILY_TRANSFER_LIMIT:
                return BankingResult(
                    False,
                    f"Amount ${amount:,.2f} exceeds maximum single transaction limit of ${config.MAX_DAILY_TRANSFER_LIMIT:,.2f}.",
                    error_code="EXCEEDS_MAX_LIMIT",
                )

            # Step-Up MFA validation check
            if amount > config.AUTO_TRANSFER_LIMIT and not step_up_token_verified:
                return BankingResult(
                    False,
                    f"Transfer of ${amount:,.2f} exceeds standard limit (${config.AUTO_TRANSFER_LIMIT:,.2f}). Out-of-band Step-Up MFA authentication required.",
                    error_code="STEP_UP_MFA_REQUIRED",
                    data={"amount": amount, "threshold": config.AUTO_TRANSFER_LIMIT},
                )

            sender = self.accounts.get(from_account_id)
            if not sender:
                return BankingResult(False, f"Source account '{from_account_id}' not found.", error_code="SENDER_NOT_FOUND")

            if sender.status != AccountStatus.ACTIVE:
                return BankingResult(False, f"Source account is currently {sender.status.value}.", error_code="ACCOUNT_INACTIVE")

            recipient = self.accounts.get(to_account_id)
            if not recipient:
                return BankingResult(False, f"Destination account '{to_account_id}' not found.", error_code="RECIPIENT_NOT_FOUND")

            if sender.balance < amount:
                return BankingResult(
                    False,
                    f"Insufficient funds. Current balance: ${sender.balance:,.2f}, required: ${amount:,.2f}.",
                    error_code="INSUFFICIENT_FUNDS",
                )

            # Atomic double-entry update
            sender.balance -= amount
            sender.daily_transferred_amount += amount
            recipient.balance += amount

            tx = TransactionRecord(
                from_account=from_account_id,
                to_account=to_account_id,
                amount=amount,
                currency=sender.currency,
                description=description,
                step_up_approved=step_up_token_verified,
            )
            self.transactions.insert(0, tx)

            return BankingResult(
                True,
                f"Successfully transferred ${amount:,.2f} from {sender.owner_name} to {recipient.owner_name}.",
                data={
                    "tx_id": tx.tx_id,
                    "from_account": from_account_id,
                    "to_account": to_account_id,
                    "amount": amount,
                    "remaining_balance": sender.balance,
                    "timestamp": tx.timestamp.isoformat(),
                },
            )

    def freeze_card(self, account_id: str) -> BankingResult:
        with self._lock:
            account = self.accounts.get(account_id)
            if not account:
                return BankingResult(False, f"Account '{account_id}' not found.", error_code="ACCOUNT_NOT_FOUND")
            if account.card_status == CardStatus.FROZEN:
                return BankingResult(True, f"Card for account {account_id} is already frozen.", data={"card_status": "FROZEN"})

            account.card_status = CardStatus.FROZEN
            return BankingResult(
                True,
                f"Debit card ({account.card_number_masked}) for {account.owner_name} has been successfully frozen.",
                data={"account_id": account_id, "card_status": "FROZEN"},
            )

    def unfreeze_card(self, account_id: str) -> BankingResult:
        with self._lock:
            account = self.accounts.get(account_id)
            if not account:
                return BankingResult(False, f"Account '{account_id}' not found.", error_code="ACCOUNT_NOT_FOUND")
            if account.card_status == CardStatus.ACTIVE:
                return BankingResult(True, f"Card for account {account_id} is already active.", data={"card_status": "ACTIVE"})

            account.card_status = CardStatus.ACTIVE
            return BankingResult(
                True,
                f"Debit card ({account.card_number_masked}) for {account.owner_name} has been successfully unfrozen and activated.",
                data={"account_id": account_id, "card_status": "ACTIVE"},
            )

    def list_transactions(self, account_id: str, limit: int = 5) -> BankingResult:
        with self._lock:
            account = self.accounts.get(account_id)
            if not account:
                return BankingResult(False, f"Account '{account_id}' not found.", error_code="ACCOUNT_NOT_FOUND")

            account_txs = [
                tx.model_dump()
                for tx in self.transactions
                if tx.from_account == account_id or tx.to_account == account_id
            ][:limit]

            # Convert datetime to string for json serialization
            for t in account_txs:
                if isinstance(t.get("timestamp"), datetime):
                    t["timestamp"] = t["timestamp"].isoformat()

            return BankingResult(
                True,
                f"Retrieved {len(account_txs)} recent transaction(s).",
                data={"transactions": account_txs},
            )


# Global singleton instance for core banking engine
bank_engine = CoreBankingService()
