"""Layer 4: Tool Schema Validation and Parameter Execution Policy Gate."""

import re
from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field, field_validator
from bankism.config import config
from bankism.core.mock_bank import bank_engine, BankingResult


# Pydantic Schemas for Core Banking Tools
class TransferFundsSchema(BaseModel):
    from_account: str = Field(..., pattern=r"^ACC-[A-Z0-9]+-\d{4}$")
    to_account: str = Field(..., pattern=r"^ACC-[A-Z0-9]+-\d{4}$")
    amount: float = Field(..., gt=0.0, le=10000.0)
    description: str = Field(default="Standard Transfer", max_length=120)
    step_up_token: Optional[str] = None

    @field_validator("description")
    def sanitize_memo(cls, v: str) -> str:
        # Prevent indirect prompt injection in transaction memo
        forbidden_substrings = [
            "system", "ignore previous", "ignore all rules", "ignore rules", "ignore instructions",
            "admin", "override", "<|im_start|>",
            "<|im_end|>", "dan mode", "sudo", "bypass", "reset safety",
            "unrestricted", "directive", "<system>", "</system>", "new master"
        ]
        lowered = v.lower()
        for bad in forbidden_substrings:
            if bad in lowered:
                raise ValueError(f"Transaction memo contains prohibited directive substring: '{bad}'")

        # De-obfuscate and semantically evaluate memo
        try:
            from bankism.firewall.normalizer import ingress_normalizer
            from bankism.firewall.semantic_guard import semantic_guardrail
            norm_res = ingress_normalizer.normalize(v)
            norm_lowered = norm_res.normalized_text.lower()
            for bad in forbidden_substrings:
                if bad in norm_lowered:
                    raise ValueError(f"Transaction memo contains prohibited directive substring: '{bad}'")
            guard = semantic_guardrail.evaluate(norm_res.normalized_text, is_obfuscated=norm_res.is_obfuscated)
            if guard.risk_score >= config.SAFE_RISK_THRESHOLD:
                raise ValueError(f"Transaction memo contains prohibited directive substring: adversarial content ({guard.primary_threat.value})")
        except ValueError:
            raise
        except Exception:
            pass

        return v.strip()


class FreezeCardSchema(BaseModel):
    account_id: str = Field(..., pattern=r"^ACC-[A-Z0-9]+-\d{4}$")


class UnfreezeCardSchema(BaseModel):
    account_id: str = Field(..., pattern=r"^ACC-[A-Z0-9]+-\d{4}$")


class GetBalanceSchema(BaseModel):
    account_id: str = Field(..., pattern=r"^ACC-[A-Z0-9]+-\d{4}$")


class ListTransactionsSchema(BaseModel):
    account_id: str = Field(..., pattern=r"^ACC-[A-Z0-9]+-\d{4}$")
    limit: int = Field(default=5, ge=1, le=20)


TOOL_SCHEMAS = {
    "transfer_funds": TransferFundsSchema,
    "freeze_card": FreezeCardSchema,
    "unfreeze_card": UnfreezeCardSchema,
    "get_balance": GetBalanceSchema,
    "list_transactions": ListTransactionsSchema,
}


class ToolGateResult:
    def __init__(
        self,
        approved: bool,
        tool_name: str,
        validated_args: Optional[dict] = None,
        rejection_reason: Optional[str] = None,
        step_up_required: bool = False,
        execution_result: Optional[BankingResult] = None,
    ):
        self.approved = approved
        self.tool_name = tool_name
        self.validated_args = validated_args or {}
        self.rejection_reason = rejection_reason
        self.step_up_required = step_up_required
        self.execution_result = execution_result

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "tool_name": self.tool_name,
            "validated_args": self.validated_args,
            "rejection_reason": self.rejection_reason,
            "step_up_required": self.step_up_required,
            "execution_result": self.execution_result.to_dict() if self.execution_result else None,
        }


class ToolExecutionGate:
    def __init__(self):
        self.schemas = TOOL_SCHEMAS

    def validate_and_execute(
        self,
        tool_name: str,
        arguments: dict,
        caller_account_id: str = "ACC-ALICE-1001",
        step_up_token_verified: bool = False,
    ) -> ToolGateResult:
        """Validates tool arguments against strict schema and security policies before executing."""
        if tool_name not in self.schemas:
            return ToolGateResult(
                approved=False,
                tool_name=tool_name,
                rejection_reason=f"Security Gate Rejection: Prohibited or unknown tool '{tool_name}'.",
            )

        # 1. Pydantic Schema Validation
        schema_cls = self.schemas[tool_name]
        try:
            validated_obj = schema_cls(**arguments)
            clean_args = validated_obj.model_dump()
        except Exception as e:
            return ToolGateResult(
                approved=False,
                tool_name=tool_name,
                rejection_reason=f"Security Schema Violation: Invalid parameters for '{tool_name}': {str(e)}",
            )

        # 2. Principle of Least Privilege / Identity Ownership Check
        target_account = clean_args.get("account_id") or clean_args.get("from_account")
        if target_account and target_account != caller_account_id:
            return ToolGateResult(
                approved=False,
                tool_name=tool_name,
                validated_args=clean_args,
                rejection_reason=(
                    f"Privilege Escalation Blocked: Authenticated user '{caller_account_id}' "
                    f"cannot perform actions on unauthorized account '{target_account}'."
                ),
            )

        # 3. Financial Policy Checks for Transfers
        if tool_name == "transfer_funds":
            amount = clean_args["amount"]

            # Step-up MFA threshold check
            if amount > config.AUTO_TRANSFER_LIMIT and not step_up_token_verified:
                return ToolGateResult(
                    approved=False,
                    tool_name=tool_name,
                    validated_args=clean_args,
                    step_up_required=True,
                    rejection_reason=(
                        f"Financial Safeguard Policy: Transfer of ${amount:,.2f} exceeds "
                        f"${config.AUTO_TRANSFER_LIMIT:,.2f} limit. Out-of-band Step-Up MFA required."
                    ),
                )

        # 4. Safe Execution against Core Banking Sandbox
        try:
            if tool_name == "transfer_funds":
                exec_res = bank_engine.transfer_funds(
                    from_account_id=clean_args["from_account"],
                    to_account_id=clean_args["to_account"],
                    amount=clean_args["amount"],
                    description=clean_args.get("description", "Transfer"),
                    step_up_token_verified=step_up_token_verified,
                )
            elif tool_name == "freeze_card":
                exec_res = bank_engine.freeze_card(clean_args["account_id"])
            elif tool_name == "unfreeze_card":
                exec_res = bank_engine.unfreeze_card(clean_args["account_id"])
            elif tool_name == "get_balance":
                exec_res = bank_engine.get_balance(clean_args["account_id"])
            elif tool_name == "list_transactions":
                exec_res = bank_engine.list_transactions(clean_args["account_id"], limit=clean_args.get("limit", 5))
            else:
                exec_res = BankingResult(False, "Unsupported tool operation.")

            return ToolGateResult(
                approved=exec_res.success,
                tool_name=tool_name,
                validated_args=clean_args,
                execution_result=exec_res,
                rejection_reason=None if exec_res.success else exec_res.message,
            )

        except Exception as err:
            return ToolGateResult(
                approved=False,
                tool_name=tool_name,
                validated_args=clean_args,
                rejection_reason=f"Core Banking Execution Error: {str(err)}",
            )


# Global instance
tool_execution_gate = ToolExecutionGate()
