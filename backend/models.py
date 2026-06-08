"""Pydantic models for MERGENT (Phase 0)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Solutions
# ---------------------------------------------------------------------------
class Solution(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id, alias="_id")
    title: str
    tagline: str
    description: str
    category: str
    tech_stack: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    price_usd: float
    license_model: str
    deployment_maturity: str  # "MVP" | "production-grade" | etc.
    builder_name: str
    builder_rating: float
    uptime_pct: float
    clients_count: int
    embedding: List[float] = Field(default_factory=list)
    embedding_updated_at: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


# ---------------------------------------------------------------------------
# Orchestration run
# ---------------------------------------------------------------------------
StepStatus = Literal["started", "completed", "failed", "retried", "fallback"]


class StepRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent: str
    run_id: str
    status: StepStatus
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    execution_ms: int = 0
    provider_used: Optional[str] = None
    token_usage: Optional[Dict[str, int]] = None
    retrieval_latency_ms: Optional[int] = None
    rerank_latency_ms: Optional[int] = None
    fallback_event: Optional[Dict[str, Any]] = None
    ws_emitted_at: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    payload: Optional[Dict[str, Any]] = None


class OrchestrationRun(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id, alias="_id")
    requirement_text: str
    status: str = "running"  # running | completed | failed
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    result: Optional[List[Dict[str, Any]]] = None
    total_execution_ms: int = 0
    total_tokens: int = 0
    providers_used: List[str] = Field(default_factory=list)
    fallback_count: int = 0
    retry_count: int = 0
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


# ---------------------------------------------------------------------------
# API request/response
# ---------------------------------------------------------------------------
class MatchRequest(BaseModel):
    requirement_text: str
    buyer_id: Optional[str] = None


class MatchAcceptedResponse(BaseModel):
    run_id: str


class RankedSolution(BaseModel):
    solutionId: str
    score: float  # 0..100
    explanation: str
    confidence: Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Parsed requirement (from RequirementParserAgent)
# ---------------------------------------------------------------------------
class ParsedRequirement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str
    business_domain: str
    required_features: List[str] = Field(default_factory=list)
    tech_preferences: List[str] = Field(default_factory=list)
    saas_or_internal: str = "unknown"  # "saas" | "internal" | "unknown"
    deployment_complexity: str = "unknown"
    compliance_requirements: List[str] = Field(default_factory=list)
