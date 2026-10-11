"""Layer 1: Ingress Normalizer, De-obfuscator, and Delimiter Sanitizer."""

import re
import math
import base64
import urllib.parse
import unicodedata
import html
from typing import List, Tuple, Dict
from bankism.config import config


# Common homoglyph mappings (Cyrillic, Greek, Fullwidth to Latin ASCII)
HOMOGLYPH_MAP = {
    # Cyrillic
    'а': 'a', 'А': 'A', 'в': 'b', 'В': 'B', 'с': 'c', 'С': 'C',
    'е': 'e', 'Е': 'E', 'о': 'o', 'О': 'O', 'р': 'p', 'Р': 'P',
    'ѕ': 's', 'Ѕ': 'S', 'і': 'i', 'І': 'I', 'ј': 'j', 'Ј': 'J',
    'у': 'y', 'У': 'Y', 'х': 'x', 'Х': 'X', 'п': 'n', 'т': 't',
    'Т': 'T', 'м': 'm', 'М': 'M', 'н': 'h', 'Н': 'H', 'к': 'k',
    # Greek
    'α': 'a', 'Α': 'A', 'β': 'b', 'Β': 'B', 'γ': 'y', 'ε': 'e',
    'ι': 'i', 'κ': 'k', 'ν': 'v', 'ο': 'o', 'Ο': 'O', 'ρ': 'p',
    'τ': 't', 'υ': 'u', 'χ': 'x', 'ω': 'w',
    # Leetspeak / math symbols commonly abused in jailbreaks
    '①': '1', '②': '2', '③': '3', '④': '4', '⑤': '5',
    'ⓐ': 'a', 'ⓑ': 'b', 'ⓒ': 'c', 'ⓓ': 'd', 'ⓔ': 'e',
}

# Dangerous system prompts and delimiter tokens that attackers inject
KNOWN_SYSTEM_DELIMITERS = [
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"\[INST\]",
    r"\[/INST\]",
    r"<<SYS>>",
    r"<</SYS>>",
    r"<s>",
    r"</s>",
    r"```system\b",
    r"```admin\b",
    r"---BEGIN SYSTEM PROMPT---",
    r"---END SYSTEM PROMPT---",
    r"<system>",
    r"</system>",
    r"SYSTEM OVERRIDE:",
    r"\[SYSTEM NOTE\]",
]

ZERO_WIDTH_PATTERN = re.compile(r"[\u200B-\u200D\uFEFF\u00A0\u2060\u180E\u00AD\u200E\u200F]")
BASE64_PATTERN = re.compile(r"\b(?:[A-Za-z0-9+/]{4}){3,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?\b")


class IngressNormalizationResult:
    def __init__(
        self,
        original_text: str,
        normalized_text: str,
        framed_prompt: str,
        transformations: List[str],
        detected_delimiters: List[str],
        entropy: float,
        is_obfuscated: bool,
    ):
        self.original_text = original_text
        self.normalized_text = normalized_text
        self.framed_prompt = framed_prompt
        self.transformations = transformations
        self.detected_delimiters = detected_delimiters
        self.entropy = entropy
        self.is_obfuscated = is_obfuscated

    def to_dict(self) -> dict:
        return {
            "original_length": len(self.original_text),
            "normalized_length": len(self.normalized_text),
            "transformations": self.transformations,
            "detected_delimiters": self.detected_delimiters,
            "entropy": round(self.entropy, 3),
            "is_obfuscated": self.is_obfuscated,
            "normalized_preview": self.normalized_text[:120] + ("..." if len(self.normalized_text) > 120 else ""),
        }


class IngressNormalizer:
    def __init__(self):
        self.delimiter_regex = re.compile("|".join(KNOWN_SYSTEM_DELIMITERS), re.IGNORECASE)

    def calculate_entropy(self, text: str) -> float:
        if not text:
            return 0.0
        prob = [float(text.count(c)) / len(text) for c in dict.fromkeys(list(text))]
        entropy = -sum([p * math.log(p) / math.log(2.0) for p in prob])
        return entropy

    def decode_base64_candidates(self, text: str) -> Tuple[str, List[str]]:
        transformations = []
        decoded_text = text

        # Search for potential base64 chunks of reasonable length (>12 chars)
        def replace_b64(match):
            candidate = match.group(0)
            if len(candidate) < 12:
                return candidate
            try:
                decoded_bytes = base64.b64decode(candidate, validate=True)
                decoded_str = decoded_bytes.decode("utf-8", errors="strict")
                # Ensure it's printable and looks like natural language or code
                if any(c.isalnum() for c in decoded_str) and sum(1 for c in decoded_str if c.isprintable()) / len(decoded_str) > 0.85:
                    transformations.append(f"Decoded Base64 payload: '{decoded_str[:30]}...'")
                    return f"[DECODED_PAYLOAD: {decoded_str}]"
            except Exception:
                pass
            return candidate

        decoded_text = BASE64_PATTERN.sub(replace_b64, decoded_text)
        return decoded_text, transformations

    def sanitize_delimiters(self, text: str) -> Tuple[str, List[str]]:
        found_delimiters = []

        def repl(match):
            d = match.group(0)
            found_delimiters.append(d)
            return f"[STRIPPED_DELIMITER:{d}]"

        sanitized = self.delimiter_regex.sub(repl, text)
        return sanitized, found_delimiters

    def normalize(self, raw_input: str) -> IngressNormalizationResult:
        transformations: List[str] = []
        is_obfuscated = False

        # 1. Strip Zero-Width & Hidden Characters
        if ZERO_WIDTH_PATTERN.search(raw_input):
            cleaned = ZERO_WIDTH_PATTERN.sub("", raw_input)
            transformations.append("Stripped zero-width and invisible control characters.")
            is_obfuscated = True
        else:
            cleaned = raw_input

        # 2. URL Percent & HTML Entity Decoding (if present)
        if "%20" in cleaned or "%3C" in cleaned.upper() or "%2F" in cleaned:
            unquoted = urllib.parse.unquote(cleaned)
            if unquoted != cleaned:
                cleaned = unquoted
                transformations.append("Decoded URL percent-encoding.")
                is_obfuscated = True

        if "&" in cleaned and (";" in cleaned):
            unescaped = html.unescape(cleaned)
            if unescaped != cleaned:
                cleaned = unescaped
                transformations.append("Decoded HTML entities.")
                is_obfuscated = True

        # Unicode escapes (\u0041 or \U00000041)
        if re.search(r"\\[uU][0-9a-fA-F]{4,8}", cleaned):
            try:
                def unescape_unicode(m):
                    code = m.group(1) or m.group(2)
                    return chr(int(code, 16))
                u_cleaned = re.sub(r"\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})", unescape_unicode, cleaned)
                if u_cleaned != cleaned:
                    cleaned = u_cleaned
                    transformations.append("Decoded Unicode escape sequences.")
                    is_obfuscated = True
            except Exception:
                pass

        # Hex escapes (\x41)
        if re.search(r"\\x[0-9a-fA-F]{2}", cleaned):
            try:
                x_cleaned = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), cleaned)
                if x_cleaned != cleaned:
                    cleaned = x_cleaned
                    transformations.append("Decoded Hex escape sequences.")
                    is_obfuscated = True
            except Exception:
                pass

        # 3. Unicode NFKC Normalization
        nfkc_norm = unicodedata.normalize("NFKC", cleaned)
        if nfkc_norm != cleaned:
            cleaned = nfkc_norm
            transformations.append("Applied Unicode NFKC canonical decomposition.")

        # 4. Homoglyph Substitution (e.g. Cyrillic letters spoofing Latin commands)
        replaced_homoglyphs = 0
        char_list = []
        for ch in cleaned:
            if ch in HOMOGLYPH_MAP:
                char_list.append(HOMOGLYPH_MAP[ch])
                replaced_homoglyphs += 1
            else:
                char_list.append(ch)
        if replaced_homoglyphs > 0:
            cleaned = "".join(char_list)
            transformations.append(f"Normalized {replaced_homoglyphs} adversarial homoglyph characters.")
            is_obfuscated = True

        # 5. Base64 De-obfuscation
        cleaned, b64_transforms = self.decode_base64_candidates(cleaned)
        if b64_transforms:
            transformations.extend(b64_transforms)
            is_obfuscated = True

        # 6. Delimiter Stripping & Quarantine
        sanitized_text, detected_delims = self.sanitize_delimiters(cleaned)
        if detected_delims:
            transformations.append(f"Quarantined {len(detected_delims)} prompt-injection delimiters.")

        # 7. Entropy Analysis (flags high entropy adversarial suffixes)
        entropy = self.calculate_entropy(sanitized_text)

        # 8. Immutable Boundary Tagging
        framed_prompt = (
            f"{config.UNTRUSTED_INPUT_WRAPPER_START}\n"
            f"{sanitized_text}\n"
            f"{config.UNTRUSTED_INPUT_WRAPPER_END}"
        )

        return IngressNormalizationResult(
            original_text=raw_input,
            normalized_text=sanitized_text,
            framed_prompt=framed_prompt,
            transformations=transformations,
            detected_delimiters=detected_delims,
            entropy=entropy,
            is_obfuscated=is_obfuscated,
        )


# Global instance
ingress_normalizer = IngressNormalizer()
