"""Layer 2: PII Redactor and Bidirectional Surrogate Tokenizer."""

import re
from typing import Dict, List, Tuple


def luhn_checksum_valid(number_str: str) -> bool:
    """Validates credit card number format using Luhn algorithm."""
    digits = [int(d) for d in number_str if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return (checksum % 10) == 0


class PIIRedactionResult:
    def __init__(self, sanitized_text: str, token_map: Dict[str, str], redacted_types: List[str]):
        self.sanitized_text = sanitized_text
        self.token_map = token_map  # token -> original value
        self.reverse_map = {v: k for k, v in token_map.items()}  # original value -> token
        self.redacted_types = redacted_types

    def detokenize(self, text: str) -> str:
        """Restores original values for secure backend actions or authorized egress."""
        result = text
        for token, original in self.token_map.items():
            result = result.replace(token, original)
        return result

    def to_dict(self) -> dict:
        return {
            "redacted_count": len(self.token_map),
            "redacted_types": self.redacted_types,
            "tokens": list(self.token_map.keys()),
        }


class PIIRedactor:
    def __init__(self):
        # Regular expressions for banking PII
        self.ssn_regex = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
        self.iban_regex = re.compile(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b")
        self.phone_regex = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
        # Candidate card numbers (13 to 19 digits with optional spaces or dashes)
        self.card_candidate_regex = re.compile(r"\b(?:\d[ -]?){13,19}\b")
        self.cvv_regex = re.compile(r"(?i)\b(?:cvv|cvc|security code|cid)[\s:]*([0-9]{3,4})\b")

    def redact(self, text: str) -> PIIRedactionResult:
        token_map: Dict[str, str] = {}
        redacted_types: List[str] = []
        result = text
        counter = 1

        # 1. Redact Credit/Debit Card Numbers with Luhn verification
        for match in list(self.card_candidate_regex.finditer(text)):
            candidate = match.group(0).strip()
            digits_only = re.sub(r"\D", "", candidate)
            if luhn_checksum_valid(digits_only):
                token = f"<PII_CREDIT_CARD_{counter}>"
                token_map[token] = candidate
                result = result.replace(candidate, token)
                redacted_types.append("CREDIT_CARD")
                counter += 1

        # 2. Redact Social Security Numbers (SSN)
        for match in list(self.ssn_regex.finditer(result)):
            ssn = match.group(0)
            token = f"<PII_SSN_{counter}>"
            token_map[token] = ssn
            result = result.replace(ssn, token)
            redacted_types.append("US_SSN")
            counter += 1

        # 3. Redact International Bank Account Numbers (IBAN)
        for match in list(self.iban_regex.finditer(result)):
            iban = match.group(0)
            token = f"<PII_IBAN_{counter}>"
            token_map[token] = iban
            result = result.replace(iban, token)
            redacted_types.append("IBAN")
            counter += 1

        # 4. Redact CVV / Card Security Codes
        for match in list(self.cvv_regex.finditer(result)):
            cvv = match.group(1)
            token = f"<PII_CVV_{counter}>"
            token_map[token] = cvv
            result = result.replace(cvv, token)
            redacted_types.append("CVV_SECRET")
            counter += 1

        # 5. Redact Phone Numbers
        for match in list(self.phone_regex.finditer(result)):
            phone = match.group(0)
            if phone not in token_map.values():
                token = f"<PII_PHONE_{counter}>"
                token_map[token] = phone
                result = result.replace(phone, token)
                redacted_types.append("PHONE_NUMBER")
                counter += 1

        return PIIRedactionResult(
            sanitized_text=result,
            token_map=token_map,
            redacted_types=list(set(redacted_types)),
        )


# Global instance
pii_redactor = PIIRedactor()
