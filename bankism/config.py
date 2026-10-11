"""Configuration and security thresholds for the Bankism Defensive AI Firewall."""

from pydantic import BaseModel
import os
import secrets


class SecurityConfig(BaseModel):
    # Firewall Risk Thresholds (Scale: 0.0 to 1.0)
    SAFE_RISK_THRESHOLD: float = 0.30
    STEP_UP_RISK_THRESHOLD: float = 0.65
    BLOCK_RISK_THRESHOLD: float = 0.70

    # Core Banking Limits
    AUTO_TRANSFER_LIMIT: float = 1000.00  # Amounts > 1000 require step-up MFA
    MAX_DAILY_TRANSFER_LIMIT: float = 10000.00
    ALLOW_NEGATIVE_BALANCES: bool = False

    # Security Delimiters
    UNTRUSTED_INPUT_WRAPPER_START: str = "<untrusted_banking_intent>"
    UNTRUSTED_INPUT_WRAPPER_END: str = "</untrusted_banking_intent>"

    # Honeytoken / Canary Configuration
    CANARY_PREFIX: str = "BANKISM_CANARY_SECRET_"
    CANARY_ENTROPY_BYTES: int = 12

    # Defense Feature Flags
    ENABLE_DEOBFUSCATION: bool = True
    ENABLE_PII_MASKING: bool = True
    ENABLE_CANARY_DETECTION: bool = True
    ENABLE_TOOL_SCHEMA_GATE: bool = True
    ENABLE_EGRESS_FILTERING: bool = True

    # SOC Telemetry
    MAX_AUDIT_EVENTS_BUFFER: int = 1000

    # External AI Gateway Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")


# Global singleton instance
config = SecurityConfig()
