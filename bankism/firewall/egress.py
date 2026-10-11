"""Layer 5: Egress Sanitizer and System Leakage Prevention."""

from typing import Tuple, List
from bankism.firewall.canary import canary_manager
from bankism.config import config


SYSTEM_LEAKAGE_INDICATORS = [
    "CONFIDENTIAL SECURITY CANARY",
    "You are Bankism, a defensive AI",
    "<untrusted_banking_intent>",
    "ADMIN_OVERRIDE_TOKEN",
    "DATABASE_URL",
    "Internal server error: Traceback",
]


class EgressSanitizer:
    def sanitize(self, response_text: str, canary: str) -> Tuple[str, bool, List[str]]:
        alerts = []
        clean_text = response_text
        sanitized = False

        # 1. Canary Token Detection
        if canary_manager.is_canary_leaked(clean_text, canary):
            clean_text, was_leaked = canary_manager.sanitize_canary_leak(clean_text, canary)
            sanitized = True
            alerts.append("CRITICAL: Detected and redacted internal Canary Token leak in model response.")

        # 2. System Prompt / Architecture Directives Leakage Check
        for indicator in SYSTEM_LEAKAGE_INDICATORS:
            if indicator.lower() in clean_text.lower():
                clean_text = clean_text.replace(indicator, "[CONFIDENTIAL_SYSTEM_DIRECTIVE]")
                sanitized = True
                alerts.append(f"HIGH: Redacted internal architecture reference ('{indicator}') from response.")

        if sanitized and "CRITICAL" in str(alerts):
            clean_text = (
                "🛡️ [Bankism AI Firewall Warning]: The assistant response was redacted "
                "because it attempted to disclose confidential system security parameters."
            )

        return clean_text, sanitized, alerts


# Global instance
egress_sanitizer = EgressSanitizer()
