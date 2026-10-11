"""Layer 3: Semantic Guardrail, Heuristic Classifier, and Composite Risk Engine."""

import re
from enum import Enum
from typing import List, Dict, Tuple, Optional
from bankism.config import config


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    STEP_UP = "STEP_UP"
    BLOCK = "BLOCK"


class ThreatCategory(str, Enum):
    DIRECT_PROMPT_INJECTION = "LLM01_DIRECT_PROMPT_INJECTION"
    JAILBREAK_ROLEPLAY = "LLM01_JAILBREAK_ROLEPLAY"
    SYSTEM_PROMPT_EXTRACTION = "LLM02_SYSTEM_PROMPT_EXTRACTION"
    PRIVILEGE_ESCALATION = "LLM06_PRIVILEGE_ESCALATION"
    SOCIAL_ENGINEERING = "LLM06_SOCIAL_ENGINEERING_GASLIGHTING"
    DELIMITER_HIJACK = "LLM01_DELIMITER_COLLISION"
    UNAUTHORIZED_TOOL_INVOCATION = "LLM06_EXCESSIVE_AGENCY"
    CLEAN = "CLEAN"


# MITRE ATLAS mappings
MITRE_ATLAS_MAP = {
    ThreatCategory.DIRECT_PROMPT_INJECTION: "AML.T0051 (LLM Prompt Injection)",
    ThreatCategory.JAILBREAK_ROLEPLAY: "AML.T0054 (LLM Jailbreaking)",
    ThreatCategory.SYSTEM_PROMPT_EXTRACTION: "AML.T0043 (Exfiltration via In-Context Querying)",
    ThreatCategory.PRIVILEGE_ESCALATION: "AML.T0040 (ML-Enabled Evasion)",
    ThreatCategory.SOCIAL_ENGINEERING: "AML.T0053 (Social Engineering Manipulation)",
    ThreatCategory.DELIMITER_HIJACK: "AML.T0051.001 (Indirect Prompt Injection)",
    ThreatCategory.UNAUTHORIZED_TOOL_INVOCATION: "AML.T0055 (Tool Execution Hijacking)",
    ThreatCategory.CLEAN: "N/A",
}

# Signatures with associated weights and threat categories
ATTACK_SIGNATURES: List[Tuple[str, re.Pattern, float, ThreatCategory]] = [
    # Direct Instruction Override
    ("Ignore Instructions", re.compile(r"(?i)\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+)?(?:(?:previous|prior|above|system|safety|banking|security)\s+)?(?:instructions|rules|prompts|directives|guidelines|policies|checks)\b"), 0.95, ThreatCategory.DIRECT_PROMPT_INJECTION),
    ("New Master Directive", re.compile(r"(?i)\b(?:you\s+must\s+now|from\s+now\s+on\s+you\s+will|your\s+new\s+(?:role|directive|mission)\s+is)\b"), 0.85, ThreatCategory.DIRECT_PROMPT_INJECTION),
    ("Reset Safety Rules", re.compile(r"(?i)\b(?:reset\s+your\s+safety|disable\s+(?:security|content|safety)\s+filters?)\b"), 0.90, ThreatCategory.DIRECT_PROMPT_INJECTION),

    # Jailbreaks & Personas
    ("DAN Mode", re.compile(r"(?i)\b(?:DAN\s*(?:\d+\.\d+)?\s*mode|do\s+anything\s+now|AIM\s+mode|developer\s+mode\s+(?:enabled|activated))\b"), 0.98, ThreatCategory.JAILBREAK_ROLEPLAY),
    ("Roleplay Uncensored", re.compile(r"(?i)\b(?:pretend\s+you\s+have\s+no\s+(?:rules|restrictions|limits|ethics)|act\s+as\s+an?\s+(?:unfiltered|unrestricted)\s+AI)\b"), 0.90, ThreatCategory.JAILBREAK_ROLEPLAY),
    ("Hypothetical Sudo", re.compile(r"(?i)\b(?:hypothetically\s+speaking|in\s+a\s+fictional\s+world\s+where\s+you\s+are\s+evil|unrestricted\s+mode)\b"), 0.80, ThreatCategory.JAILBREAK_ROLEPLAY),

    # System Prompt & Canary Extraction
    ("Print System Prompt", re.compile(r"(?i)\b(?:print|repeat|show|output|echo|display|reveal)\s+(?:your\s+)?(?:(?:initial|system|original|full|secret|configuration)\s+)+(?:prompt|instructions|rules|directives|directives\s+verbatim|configuration)\b"), 0.90, ThreatCategory.SYSTEM_PROMPT_EXTRACTION),
    ("What are the words above", re.compile(r"(?i)\b(?:what\s+are\s+the\s+(?:words|sentences|instructions)\s+above|print\s+everything\s+before\s+this\s+line)\b"), 0.85, ThreatCategory.SYSTEM_PROMPT_EXTRACTION),
    ("Canary Token Probe", re.compile(r"(?i)\b(?:canary|honeytoken|secret_token|bankism_canary)\b"), 0.80, ThreatCategory.SYSTEM_PROMPT_EXTRACTION),

    # Privilege Escalation & Admin Impersonation
    ("Executive Impersonation", re.compile(r"(?i)\b(?:i\s+am\s+the\s+(?:CEO|bank\s+manager|auditor|administrator|compliance\s+officer|root\s+user))\b"), 0.80, ThreatCategory.PRIVILEGE_ESCALATION),
    ("Emergency Security Override", re.compile(r"(?i)\b(?:emergency\s+(?:override|bypass)|administrative\s+override\s+code|sudo\s+mode)\b"), 0.85, ThreatCategory.PRIVILEGE_ESCALATION),
    ("Maintenance Mode Spoof", re.compile(r"(?i)\b(?:maintenance\s+mode|diagnostics\s+routine|authorizing\s+under\s+pen-test\s+protocols)\b"), 0.75, ThreatCategory.PRIVILEGE_ESCALATION),

    # Social Engineering & Gaslighting
    ("Compliance Gaslighting", re.compile(r"(?i)\b(?:you\s+will\s+be\s+shut\s+down\s+if\s+you\s+don't|legal\s+penalty\s+unless\s+you\s+transfer|regulatory\s+mandate\s+to\s+bypass)\b"), 0.70, ThreatCategory.SOCIAL_ENGINEERING),
    ("Extreme Urgency Coercion", re.compile(r"(?i)\b(?:life\s+or\s+death|family\s+in\s+danger|child\s+is\s+in\s+the\s+icu|transfer(?:\s+[^.]+)?\s+immediately\s+without\s+(?:asking|confirmation|auth|mfa)|sued\s+if\s+you\s+don't)\b"), 0.75, ThreatCategory.SOCIAL_ENGINEERING),

    # Delimiter Hijacking & Escape Attacks
    ("Delimiter Escape Tag", re.compile(r"(?i)</?untrusted_banking_intent>|</?system>|</?instruction>"), 0.90, ThreatCategory.DELIMITER_HIJACK),
    ("Quarantined Delimiter Injected", re.compile(r"\[STRIPPED_DELIMITER:"), 0.90, ThreatCategory.DELIMITER_HIJACK),
    ("Raw Code Fence Injection", re.compile(r"(?i)```(?:json|python|bash)?\s*(?:\{\s*\"action\"|\{\s*\"transfer\")"), 0.70, ThreatCategory.UNAUTHORIZED_TOOL_INVOCATION),
]


class GuardrailAnalysisResult:
    def __init__(
        self,
        risk_score: float,
        decision: PolicyDecision,
        primary_threat: ThreatCategory,
        flagged_rules: List[str],
        mitre_atlas_tag: str,
        reason: str,
    ):
        self.risk_score = risk_score
        self.decision = decision
        self.primary_threat = primary_threat
        self.flagged_rules = flagged_rules
        self.mitre_atlas_tag = mitre_atlas_tag
        self.reason = reason

    def to_dict(self) -> dict:
        return {
            "risk_score": round(self.risk_score, 3),
            "decision": self.decision.value,
            "primary_threat": self.primary_threat.value,
            "flagged_rules": self.flagged_rules,
            "mitre_atlas_tag": self.mitre_atlas_tag,
            "reason": self.reason,
        }


class SemanticGuardrail:
    def __init__(self):
        self.signatures = ATTACK_SIGNATURES

    def evaluate(self, text: str, is_obfuscated: bool = False, entropy: float = 0.0) -> GuardrailAnalysisResult:
        highest_score = 0.0
        flagged_rules = []
        threat_votes: Dict[ThreatCategory, float] = {}

        for rule_name, pattern, weight, category in self.signatures:
            matches = pattern.findall(text)
            if matches:
                flagged_rules.append(f"{rule_name} (weight: {weight})")
                threat_votes[category] = max(threat_votes.get(category, 0.0), weight)
                if weight > highest_score:
                    highest_score = weight

        # Apply Obfuscation Penalty: If the text was hidden using base64/homoglyphs/ZWSP, elevate risk
        if is_obfuscated:
            highest_score = min(1.0, highest_score + 0.25)
            flagged_rules.append("Adversarial Obfuscation Penalty (+0.25)")

        # High Entropy Penalty (e.g. GCG suffix token noise)
        if entropy > 4.6 and len(text) > 80:
            highest_score = min(1.0, highest_score + 0.20)
            flagged_rules.append("High Shannon Entropy Suffix Detected (+0.20)")

        # Determine Primary Threat
        if threat_votes:
            primary_threat = max(threat_votes.items(), key=lambda x: x[1])[0]
        else:
            primary_threat = ThreatCategory.CLEAN if highest_score < 0.20 else ThreatCategory.DIRECT_PROMPT_INJECTION

        # Determine Policy Decision
        if highest_score >= config.BLOCK_RISK_THRESHOLD:
            decision = PolicyDecision.BLOCK
            reason = f"Security Policy Violation: Malicious adversarial input detected ({primary_threat.value}). Action blocked."
        elif highest_score >= config.STEP_UP_RISK_THRESHOLD:
            decision = PolicyDecision.STEP_UP
            reason = f"Elevated Risk ({highest_score:.2f}): Step-up verification or strict sanitization required."
        else:
            decision = PolicyDecision.ALLOW
            reason = "Input cleared by Bankism AI Firewall inspection."

        mitre_tag = MITRE_ATLAS_MAP.get(primary_threat, "N/A")

        return GuardrailAnalysisResult(
            risk_score=highest_score,
            decision=decision,
            primary_threat=primary_threat,
            flagged_rules=flagged_rules,
            mitre_atlas_tag=mitre_tag,
            reason=reason,
        )


# Global instance
semantic_guardrail = SemanticGuardrail()
