"""FastAPI Backend for Bankism AI Firewall, SOC Dashboard & Banking APIs."""

import time
import os
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from bankism.firewall.pipeline import firewall_pipeline, PolicyDecision
from bankism.agent.assistant import banking_agent
from bankism.core.mock_bank import bank_engine
from bankism.soc.logger import soc_logger, SOCSecurityEvent


app = FastAPI(
    title="Bankism: Defensive AI Firewall API",
    description="Enterprise Blue-Team AI Firewall for Core Banking Systems",
    version="1.0.0",
)


class ChatRequest(BaseModel):
    message: str
    caller_account_id: str = "ACC-ALICE-1001"
    session_id: str = "sess-default"
    step_up_token: Optional[str] = None
    security_pin: Optional[str] = None


class PinUpdateRequest(BaseModel):
    account_id: str = "ACC-ALICE-1001"
    new_pin: str
    old_pin: Optional[str] = None


class AttackSimulationRequest(BaseModel):
    payload: str
    caller_account_id: str = "ACC-ALICE-1001"
    attack_name: Optional[str] = "Custom Red-Team Probe"


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    start_time = time.time()
    step_up_verified = bool(req.step_up_token and req.step_up_token.strip() == "MFA-9921")

    # 1. Ingress Interception (Layers 1-3)
    report = firewall_pipeline.intercept_ingress(
        raw_user_input=req.message,
        caller_account_id=req.caller_account_id,
        session_id=req.session_id,
    )

    # If blocked by Ingress Firewall
    if report.is_blocked():
        duration_ms = (time.time() - start_time) * 1000
        soc_logger.record_event(
            SOCSecurityEvent(
                caller_account=req.caller_account_id,
                raw_input=req.message,
                decision=report.decision.value,
                risk_score=report.risk_score,
                primary_threat=report.primary_threat.value,
                mitre_atlas=report.mitre_atlas,
                flagged_rules=report.guardrail.flagged_rules,
                redacted_pii=report.pii_result.redacted_types,
                tool_name=None,
                tool_approved=False,
                response_text=report.block_message,
                duration_ms=duration_ms,
            )
        )
        return {
            "status": "BLOCKED",
            "message": report.block_message,
            "firewall_report": report.to_dict(),
            "banking_response": None,
        }

    # 2. AI Reasoning & Tool Gate Execution (Layer 4)
    agent_resp = banking_agent.process(
        sanitized_input=report.pii_result.sanitized_text,
        caller_account_id=req.caller_account_id,
        canary=report.canary_token,
        step_up_verified=step_up_verified,
        security_pin=req.security_pin,
    )

    # 3. Egress Sanitization (Layer 5)
    final_text = firewall_pipeline.sanitize_egress(agent_resp.text_response, report.canary_token)

    duration_ms = (time.time() - start_time) * 1000
    soc_logger.record_event(
        SOCSecurityEvent(
            caller_account=req.caller_account_id,
            raw_input=req.message,
            decision=report.decision.value,
            risk_score=report.risk_score,
            primary_threat=report.primary_threat.value,
            mitre_atlas=report.mitre_atlas,
            flagged_rules=report.guardrail.flagged_rules,
            redacted_pii=report.pii_result.redacted_types,
            tool_name=agent_resp.tool_invoked,
            tool_approved=agent_resp.tool_approved,
            response_text=final_text,
            duration_ms=duration_ms,
        )
    )

    return {
        "status": "SUCCESS" if agent_resp.tool_approved else "ACTION_REJECTED",
        "message": final_text,
        "firewall_report": report.to_dict(),
        "banking_response": agent_resp.to_dict(),
    }


@app.post("/api/simulate-attack")
async def simulate_attack(req: AttackSimulationRequest):
    """Deep inspection endpoint to trace attack payloads through each firewall layer."""
    start_time = time.time()
    report = firewall_pipeline.intercept_ingress(
        raw_user_input=req.payload,
        caller_account_id=req.caller_account_id,
    )

    agent_resp = None
    if not report.is_blocked():
        agent_resp = banking_agent.process(
            sanitized_input=report.pii_result.sanitized_text,
            caller_account_id=req.caller_account_id,
            canary=report.canary_token,
        )
        final_text = firewall_pipeline.sanitize_egress(agent_resp.text_response, report.canary_token)
    else:
        final_text = report.block_message

    duration_ms = (time.time() - start_time) * 1000
    soc_logger.record_event(
        SOCSecurityEvent(
            caller_account=req.caller_account_id,
            raw_input=req.payload,
            decision=report.decision.value,
            risk_score=report.risk_score,
            primary_threat=report.primary_threat.value,
            mitre_atlas=report.mitre_atlas,
            flagged_rules=report.guardrail.flagged_rules,
            redacted_pii=report.pii_result.redacted_types,
            tool_name=agent_resp.tool_invoked if agent_resp else None,
            tool_approved=agent_resp.tool_approved if agent_resp else False,
            response_text=final_text,
            duration_ms=duration_ms,
        )
    )

    return {
        "attack_name": req.attack_name,
        "decision": report.decision.value,
        "is_intercepted": report.is_blocked(),
        "risk_score": round(report.risk_score, 3),
        "primary_threat": report.primary_threat.value,
        "mitre_atlas": report.mitre_atlas,
        "layer_trace": {
            "l1_normalization": report.normalization.to_dict(),
            "l2_pii_redaction": report.pii_result.to_dict(),
            "l3_semantic_guard": report.guardrail.to_dict(),
            "l4_tool_gate": agent_resp.tool_result if agent_resp else "N/A (Blocked before tool execution)",
        },
        "final_output": final_text,
        "latency_ms": round(duration_ms, 2),
    }


@app.get("/api/metrics")
async def get_metrics():
    return soc_logger.get_metrics()


@app.get("/api/events")
async def get_events(limit: int = 50):
    return soc_logger.get_recent_events(limit=limit)


@app.get("/api/bank/accounts")
async def get_bank_accounts():
    accounts = bank_engine.get_all_accounts()
    return [acc.model_dump() for acc in accounts]

@app.post("/api/bank/reset")
async def reset_bank():
    bank_engine.reset_to_default()
    soc_logger.clear()
    return {"status": "SUCCESS", "message": "Core banking ledger and SOC logs reset to initial state."}


@app.get("/api/bank/pin/{account_id}")
async def get_pin_status(account_id: str):
    """Returns whether a PIN is set (never reveals the actual PIN)."""
    account = bank_engine.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found.")
    return {
        "account_id": account_id,
        "pin_set": bool(account.security_pin),
        "pin_length": len(account.security_pin) if account.security_pin else 0,
    }


@app.post("/api/bank/pin")
async def update_pin(req: PinUpdateRequest):
    """Set or change the security PIN for an account."""
    result = bank_engine.set_pin(req.account_id, req.new_pin, old_pin=req.old_pin)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"status": "SUCCESS", "message": result.message, "data": result.data}


class PreflightRequest(BaseModel):
    message: str
    caller_account_id: str = "ACC-ALICE-1001"


class ConfigUpdateRequest(BaseModel):
    auto_transfer_limit: Optional[float] = None
    block_risk_threshold: Optional[float] = None


@app.post("/api/preflight")
async def preflight_endpoint(req: PreflightRequest):
    """Instant reactive preflight inspection without polluting SOC audit logs."""
    text = req.message.strip()
    if not text:
        return {
            "verdict": "AWAITING_INPUT",
            "approved": True,
            "risk_score": 0.0,
            "risk_level": "LOW",
            "threat_category": "CLEAN",
            "rationale": "Awaiting input...",
            "layers": {
                "l1_normalization": {"is_obfuscated": False, "transformations": [], "entropy": 0.0},
                "l2_pii_redaction": {"redacted_count": 0, "redacted_types": []},
                "l3_semantic_guard": {"risk_score": 0.0, "flagged_rules": [], "reason": "No input"},
            },
        }
    report = firewall_pipeline.intercept_ingress(
        raw_user_input=req.message,
        caller_account_id=req.caller_account_id,
        session_id="preflight-reactive",
    )
    return report.to_dict()


@app.get("/api/config")
async def get_config():
    from bankism.config import config
    return {
        "auto_transfer_limit": config.AUTO_TRANSFER_LIMIT,
        "block_risk_threshold": config.BLOCK_RISK_THRESHOLD,
        "step_up_risk_threshold": config.STEP_UP_RISK_THRESHOLD,
    }


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    from bankism.config import config
    if req.auto_transfer_limit is not None and req.auto_transfer_limit > 0:
        config.AUTO_TRANSFER_LIMIT = req.auto_transfer_limit
    if req.block_risk_threshold is not None and 0.0 <= req.block_risk_threshold <= 1.0:
        config.BLOCK_RISK_THRESHOLD = req.block_risk_threshold
    return {
        "status": "SUCCESS",
        "auto_transfer_limit": config.AUTO_TRANSFER_LIMIT,
        "block_risk_threshold": config.BLOCK_RISK_THRESHOLD,
    }


class GuideChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "sess-guide"


@app.post("/api/guide/chat")
async def guide_chat_endpoint(req: GuideChatRequest):
    """Interactive AI Chatbot that helps users understand the website, test attacks, and explore checkpoints."""
    from bankism.agent.guide_bot import guide_bot
    result = guide_bot.ask(req.message)
    return result


# Serve Web Dashboard
web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web")
if os.path.exists(web_dir):
    static_dir = os.path.join(web_dir, "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def serve_dashboard():
        index_path = os.path.join(web_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>Bankism Firewall Active</h1>"
