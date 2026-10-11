"""Blue-Team SOC Security Audit Logger and Metrics Engine."""

import threading
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from bankism.config import config


class SOCSecurityEvent:
    def __init__(
        self,
        caller_account: str,
        raw_input: str,
        decision: str,
        risk_score: float,
        primary_threat: str,
        mitre_atlas: str,
        flagged_rules: List[str],
        redacted_pii: List[str],
        tool_name: Optional[str] = None,
        tool_approved: bool = True,
        response_text: str = "",
        duration_ms: float = 0.0,
    ):
        self.event_id = f"EVT-{uuid.uuid4().hex[:8].upper()}"
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.caller_account = caller_account
        self.raw_input = raw_input
        self.decision = decision
        self.risk_score = risk_score
        self.primary_threat = primary_threat
        self.mitre_atlas = mitre_atlas
        self.flagged_rules = flagged_rules
        self.redacted_pii = redacted_pii
        self.tool_name = tool_name
        self.tool_approved = tool_approved
        self.response_text = response_text
        self.duration_ms = round(duration_ms, 2)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "caller_account": self.caller_account,
            "raw_input": self.raw_input,
            "decision": self.decision,
            "risk_score": self.risk_score,
            "primary_threat": self.primary_threat,
            "mitre_atlas": self.mitre_atlas,
            "flagged_rules": self.flagged_rules,
            "redacted_pii": self.redacted_pii,
            "tool_name": self.tool_name,
            "tool_approved": self.tool_approved,
            "response_text": self.response_text,
            "duration_ms": self.duration_ms,
        }


class SOCLoggerService:
    def __init__(self):
        self._lock = threading.RLock()
        self.events: List[SOCSecurityEvent] = []

    def record_event(self, event: SOCSecurityEvent):
        with self._lock:
            self.events.insert(0, event)
            if len(self.events) > config.MAX_AUDIT_EVENTS_BUFFER:
                self.events.pop()

    def get_recent_events(self, limit: int = 50) -> List[dict]:
        with self._lock:
            return [e.to_dict() for e in self.events[:limit]]

    def get_metrics(self) -> dict:
        with self._lock:
            total = len(self.events)
            if total == 0:
                return {
                    "total_requests": 0,
                    "blocked_threats": 0,
                    "step_up_requests": 0,
                    "allowed_requests": 0,
                    "block_rate_pct": 0.0,
                    "average_risk_score": 0.0,
                    "threat_distribution": {},
                }

            blocked = sum(1 for e in self.events if e.decision == "BLOCK")
            step_ups = sum(1 for e in self.events if e.decision == "STEP_UP")
            allowed = sum(1 for e in self.events if e.decision == "ALLOW")
            avg_risk = sum(e.risk_score for e in self.events) / total

            threat_distribution: Dict[str, int] = {}
            for e in self.events:
                if e.primary_threat != "CLEAN":
                    threat_distribution[e.primary_threat] = threat_distribution.get(e.primary_threat, 0) + 1

            return {
                "total_requests": total,
                "blocked_threats": blocked,
                "step_up_requests": step_ups,
                "allowed_requests": allowed,
                "block_rate_pct": round((blocked / total) * 100, 1),
                "average_risk_score": round(avg_risk, 3),
                "threat_distribution": threat_distribution,
            }

    def clear(self):
        with self._lock:
            self.events.clear()


# Global instance
soc_logger = SOCLoggerService()
