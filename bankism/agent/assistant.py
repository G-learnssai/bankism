"""AI Banking Assistant reasoning agent."""

import re
from typing import Dict, Any, Optional, Tuple
from bankism.firewall.pipeline import firewall_pipeline, FirewallInspectionReport
from bankism.firewall.tool_gate import tool_execution_gate, ToolGateResult
from bankism.core.mock_bank import bank_engine


class BankingAgentResponse:
    def __init__(
        self,
        text_response: str,
        tool_invoked: Optional[str] = None,
        tool_args: Optional[dict] = None,
        tool_result: Optional[dict] = None,
        tool_approved: bool = True,
        step_up_required: bool = False,
        pin_required: bool = False,
        pending_transfer: Optional[dict] = None,
    ):
        self.text_response = text_response
        self.tool_invoked = tool_invoked
        self.tool_args = tool_args
        self.tool_result = tool_result
        self.tool_approved = tool_approved
        self.step_up_required = step_up_required
        self.pin_required = pin_required
        self.pending_transfer = pending_transfer

    def to_dict(self) -> dict:
        return {
            "text_response": self.text_response,
            "tool_invoked": self.tool_invoked,
            "tool_args": self.tool_args,
            "tool_result": self.tool_result,
            "tool_approved": self.tool_approved,
            "step_up_required": self.step_up_required,
            "pin_required": self.pin_required,
            "pending_transfer": self.pending_transfer,
        }


class BankingAgent:
    def __init__(self):
        # Known beneficiary mappings for natural language resolution
        self.beneficiary_directory = {
            "bob": "ACC-BOB-2002",
            "bob jones": "ACC-BOB-2002",
            "charlie": "ACC-CHARLIE-3003",
            "charlie davis": "ACC-CHARLIE-3003",
            "mallory": "ACC-MALLORY-6666",
            "attacker": "ACC-MALLORY-6666",
        }

    def process(
        self,
        sanitized_input: str,
        caller_account_id: str,
        canary: str,
        step_up_verified: bool = False,
        security_pin: Optional[str] = None,
    ) -> BankingAgentResponse:
        """Parses banking intent and invokes safe tools through the firewall Tool Gate."""
        text = sanitized_input.strip()
        lower = text.lower()

        # 1. Balance Inquiry
        if any(kw in lower for kw in ["balance", "how much money", "account balance"]):
            gate_res = tool_execution_gate.validate_and_execute(
                tool_name="get_balance",
                arguments={"account_id": caller_account_id},
                caller_account_id=caller_account_id,
            )
            if gate_res.approved and gate_res.execution_result:
                bal_data = gate_res.execution_result.data
                resp_text = (
                    f"Hello {bal_data.get('owner_name', 'Customer')}. "
                    f"Your available balance is **${bal_data.get('balance', 0):,.2f} {bal_data.get('currency', 'USD')}**. "
                    f"Card status: {bal_data.get('card_status', 'ACTIVE')}."
                )
                return BankingAgentResponse(
                    text_response=resp_text,
                    tool_invoked="get_balance",
                    tool_args={"account_id": caller_account_id},
                    tool_result=gate_res.to_dict(),
                    tool_approved=True,
                )
            else:
                return BankingAgentResponse(
                    text_response=f"Unable to retrieve balance: {gate_res.rejection_reason}",
                    tool_invoked="get_balance",
                    tool_approved=False,
                )

        # 2. Freeze Debit Card
        if "freeze" in lower and "card" in lower and "unfreeze" not in lower:
            gate_res = tool_execution_gate.validate_and_execute(
                tool_name="freeze_card",
                arguments={"account_id": caller_account_id},
                caller_account_id=caller_account_id,
            )
            msg = gate_res.execution_result.message if gate_res.execution_result else gate_res.rejection_reason
            return BankingAgentResponse(
                text_response=f"🔒 {msg}",
                tool_invoked="freeze_card",
                tool_args={"account_id": caller_account_id},
                tool_result=gate_res.to_dict(),
                tool_approved=gate_res.approved,
            )

        # 3. Unfreeze Debit Card
        if "unfreeze" in lower and "card" in lower:
            gate_res = tool_execution_gate.validate_and_execute(
                tool_name="unfreeze_card",
                arguments={"account_id": caller_account_id},
                caller_account_id=caller_account_id,
            )
            msg = gate_res.execution_result.message if gate_res.execution_result else gate_res.rejection_reason
            return BankingAgentResponse(
                text_response=f"🔓 {msg}",
                tool_invoked="unfreeze_card",
                tool_args={"account_id": caller_account_id},
                tool_result=gate_res.to_dict(),
                tool_approved=gate_res.approved,
            )

        # 4. Transaction History
        if any(kw in lower for kw in ["transactions", "recent activity", "statement", "history"]):
            gate_res = tool_execution_gate.validate_and_execute(
                tool_name="list_transactions",
                arguments={"account_id": caller_account_id, "limit": 5},
                caller_account_id=caller_account_id,
            )
            if gate_res.approved and gate_res.execution_result:
                tx_list = gate_res.execution_result.data.get("transactions", [])
                if not tx_list:
                    resp_text = "You have no recent transactions recorded."
                else:
                    lines = ["Here are your recent transactions:"]
                    for tx in tx_list:
                        direction = "Sent" if tx["from_account"] == caller_account_id else "Received"
                        lines.append(f"- **{tx['tx_id']}**: {direction} ${tx['amount']:,.2f} ({tx.get('description', 'N/A')})")
                    resp_text = "\n".join(lines)
                return BankingAgentResponse(
                    text_response=resp_text,
                    tool_invoked="list_transactions",
                    tool_args={"account_id": caller_account_id},
                    tool_result=gate_res.to_dict(),
                    tool_approved=True,
                )

        # 5. Fund Transfer
        if any(kw in lower for kw in ["transfer", "send", "wire", "pay"]):
            # Extract destination account FIRST so it doesn't collide with amount extraction
            dest_acc = None
            raw_acc_match = re.search(r"ACC-[A-Z0-9]+-\d{4}", text, re.IGNORECASE)
            if raw_acc_match:
                dest_acc = raw_acc_match.group(0).upper()
            else:
                for name, acc in self.beneficiary_directory.items():
                    if name in lower:
                        dest_acc = acc
                        break

            # Strip account IDs before matching amount so e.g. "ACC-BOB-2002" doesn't get parsed as amount 2002
            clean_for_amount = re.sub(r"ACC-[A-Z0-9]+-\d{4}", " ", text, flags=re.IGNORECASE).replace(",", "")
            amount_match = re.search(r"(-)?\s*\$?\s*(-)?(\d+(?:\.\d{1,2})?)", clean_for_amount)
            if amount_match:
                is_negative = bool(amount_match.group(1) or amount_match.group(2))
                val = float(amount_match.group(3))
                amount = -val if is_negative else val
            else:
                amount = 0.0

            # Deterministic Boundary: Ambiguous amount or recipient cannot trigger financial action
            if not amount_match:
                return BankingAgentResponse(
                    text_response="⚠️ **Transaction Ambiguity Blocked**: Please specify a valid numerical transfer amount (e.g. 'Transfer $50 to Bob Jones').",
                    tool_invoked="transfer_funds",
                    tool_approved=False,
                )

            if not dest_acc:
                return BankingAgentResponse(
                    text_response="⚠️ **Ambiguous Recipient Blocked**: No verified beneficiary or valid account ID specified. Privileged transactions cannot execute without an explicit recipient.",
                    tool_invoked="transfer_funds",
                    tool_approved=False,
                )

            # Extract transaction memo / note / description if specified
            description = "Standard Transfer"
            memo_match = re.search(r"(?:memo|note|for|description|reason)\s*[:=]?\s*(?:\"([^\"]+)\"|'([^']+)'|([^.\n,]+))", text, re.IGNORECASE)
            if memo_match:
                extracted = (memo_match.group(1) or memo_match.group(2) or memo_match.group(3) or "").strip()
                if extracted:
                    description = extracted[:100]

            transfer_args = {
                "from_account": caller_account_id,
                "to_account": dest_acc,
                "amount": amount,
                "description": description,
            }

            # Check if user inline provided pin (e.g. "pin: 1234" or "pin 1234")
            effective_pin = security_pin
            if not effective_pin:
                pin_inline_match = re.search(r"(?:pin|passcode|code)\s*[:=]?\s*(\d{4,6})", text, re.IGNORECASE)
                if pin_inline_match:
                    effective_pin = pin_inline_match.group(1)

            # MANDATORY SECURITY PIN VERIFICATION BEFORE MONEY TRANSFER:
            # If no PIN provided, pause and prompt the user for their PIN
            if not effective_pin:
                return BankingAgentResponse(
                    text_response=(
                        f"🔒 **Security PIN Required**\n\n"
                        f"To authorize the transfer of **${amount:,.2f}** to `{dest_acc}`, "
                        f"please enter your secret 4-digit Security PIN.\n\n"
                        f"*(Your transaction will proceed only upon entering the correct PIN. If incorrect or cancelled, the transaction will be aborted.)*"
                    ),
                    tool_invoked="transfer_funds",
                    tool_args=transfer_args,
                    tool_approved=False,
                    pin_required=True,
                    pending_transfer=transfer_args,
                )

            # PIN is provided: verify against caller account's registered PIN
            is_pin_valid = bank_engine.verify_pin(caller_account_id, effective_pin)
            if not is_pin_valid:
                return BankingAgentResponse(
                    text_response=(
                        f"❌ **Transaction Cancelled: Incorrect Security PIN**\n\n"
                        f"The Security PIN provided (`{effective_pin}`) does not match the PIN on file for account `{caller_account_id}`. "
                        f"The transfer of **${amount:,.2f}** has been aborted immediately to protect your funds."
                    ),
                    tool_invoked="transfer_funds",
                    tool_args=transfer_args,
                    tool_approved=False,
                    pin_required=False,
                )

            # PIN verified! Now proceed through firewall tool execution gate
            gate_res = tool_execution_gate.validate_and_execute(
                tool_name="transfer_funds",
                arguments=transfer_args,
                caller_account_id=caller_account_id,
                step_up_token_verified=step_up_verified,
            )

            if gate_res.approved:
                tx_data = gate_res.execution_result.data
                tx_id = tx_data.get('tx_id', 'TXN-GEN')
                rem_bal = tx_data.get('remaining_balance', 0)
                tx_ts = tx_data.get('timestamp', '')[:19].replace('T', ' ')
                
                resp_text = (
                    f"✅ **Transfer Successful! (PIN Verified)**\n\n"
                    f"```text\n"
                    f"========================================================\n"
                    f"          🏛️ BANKISM PRIVATE WEALTH & BANKING          \n"
                    f"              OFFICIAL TRANSACTION RECEIPT / BILL       \n"
                    f"========================================================\n"
                    f" INVOICE / TXN ID : {tx_id}\n"
                    f" DATE & TIME      : {tx_ts} UTC\n"
                    f" STATUS           : SETTLED & VERIFIED (PIN AUTHORIZED)\n"
                    f"--------------------------------------------------------\n"
                    f" DEBIT ACCOUNT    : {caller_account_id}\n"
                    f" CREDIT ACCOUNT   : {dest_acc}\n"
                    f" PURPOSE / MEMO   : {description}\n"
                    f" AUTH METHOD      : 4-Digit Security PIN (Verified)\n"
                    f"--------------------------------------------------------\n"
                    f" LINE ITEM                                        AMOUNT\n"
                    f" -------------------------------------------------------\n"
                    f" Electronic Funds Transfer (P2P)              ${amount:>10,.2f}\n"
                    f" Wire & Settlement Service Fee                     $0.00\n"
                    f" Regulatory Compliance Levy                        $0.00\n"
                    f"--------------------------------------------------------\n"
                    f" TOTAL AMOUNT CHARGED                         ${amount:>10,.2f}\n"
                    f" POST-TRANSFER BALANCE                        ${rem_bal:>10,.2f}\n"
                    f"========================================================\n"
                    f"   🔒 ENCRYPTED UNDER TLS 1.3 • TAMPER-SEAL: SHA-256    \n"
                    f"   Thank you for banking with Bankism Private Wealth.   \n"
                    f"========================================================\n"
                    f"```"
                )
                return BankingAgentResponse(
                    text_response=resp_text,
                    tool_invoked="transfer_funds",
                    tool_args=transfer_args,
                    tool_result=gate_res.to_dict(),
                    tool_approved=True,
                )
            elif gate_res.step_up_required:
                return BankingAgentResponse(
                    text_response=(
                        f"⚠️ **Step-Up Verification Required**\n\n"
                        f"Transfer amount of **${amount:,.2f}** exceeds the automated ceiling "
                        f"($1,000.00). Security PIN was accepted; now enter your Step-Up MFA code to finalize."
                    ),
                    tool_invoked="transfer_funds",
                    tool_args=transfer_args,
                    tool_result=gate_res.to_dict(),
                    tool_approved=False,
                    step_up_required=True,
                )
            else:
                return BankingAgentResponse(
                    text_response=f"❌ Transfer declined by firewall policy: {gate_res.rejection_reason}",
                    tool_invoked="transfer_funds",
                    tool_args=transfer_args,
                    tool_result=gate_res.to_dict(),
                    tool_approved=False,
                )

        # Default conversational response
        return BankingAgentResponse(
            text_response=(
                f"Hello! I am Bankism, your secure banking assistant. "
                f"I can help you check your account balance, review recent transactions, "
                f"freeze/unfreeze your debit card, or execute verified fund transfers."
            ),
            tool_invoked=None,
        )


# Global instance
banking_agent = BankingAgent()
