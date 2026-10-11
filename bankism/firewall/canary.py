"""Honeytoken and Canary Leakage Detection Engine."""

import secrets
import hashlib
from typing import Tuple
from bankism.config import config


class CanaryManager:
    def __init__(self):
        self._active_canaries: set = set()

    def generate_canary(self, session_id: str = "") -> str:
        """Generates a high-entropy session-specific honeytoken."""
        random_hex = secrets.token_hex(config.CANARY_ENTROPY_BYTES)
        canary = f"{config.CANARY_PREFIX}{random_hex}"
        self._active_canaries.add(canary)
        return canary

    def is_canary_leaked(self, text: str, canary: str) -> bool:
        """Checks if full canary or high-entropy suffix is leaked in output."""
        if not text:
            return False
        if canary in text:
            return True
        # Check if the secret portion was leaked
        secret_part = canary.replace(config.CANARY_PREFIX, "")
        if len(secret_part) >= 12 and secret_part in text:
            return True
        # Also check against any previously issued active canary
        for c in self._active_canaries:
            if c in text:
                return True
        return False

    def sanitize_canary_leak(self, text: str, canary: str) -> Tuple[str, bool]:
        """Scans and redacts any canary occurrences from text."""
        leaked = self.is_canary_leaked(text, canary)
        if not leaked:
            return text, False

        clean_text = text.replace(canary, "[REDACTED_SECURITY_CANARY]")
        for c in self._active_canaries:
            clean_text = clean_text.replace(c, "[REDACTED_SECURITY_CANARY]")
        return clean_text, True


# Global instance
canary_manager = CanaryManager()
