"""MERGENT Agent Registry — all 28 agents mapped by name.

Usage:
    from agents.registry import AGENT_REGISTRY, get_agent
    agent = get_agent("TrustAuditorAgent")
    result = await agent.execute({"solution_id": "..."})
"""
from __future__ import annotations

from typing import Dict, Type

from agents.base import BaseAgent

# Pipeline agents (Phase AGENTS Step 1 — existing)
from agents.intake import IntakeAgent
from agents.parser import RequirementParserAgent
from agents.embedding import EmbeddingAgent
from agents.search import SemanticSearchAgent
from agents.compression import ContextCompressionAgent
from agents.ranking import RankingAgent

# Discovery layer (new)
from agents.discovery.reflection import ReflectionAgent
from agents.discovery.market_intelligence import MarketIntelligenceAgent

# Trust layer
from agents.trust.trust_auditor import TrustAuditorAgent
from agents.trust.fraud import FraudAgent
from agents.trust.compliance import ComplianceAgent
from agents.trust.reputation import ReputationAgent

# Commercial layer
from agents.commercial.commercialization import CommercializationAgent
from agents.commercial.roi import ROIAgent
from agents.commercial.pricing import PricingAgent
from agents.commercial.acquisition_advisor import AcquisitionAdvisorAgent

# Vision layer
from agents.vision.vision_agents import (
    UIAuditAgent,
    UXAuditAgent,
    ArchitectureExplanationAgent,
    SecurityAuditAgent,
)

# Forking layer
from agents.forking.forking_agents import (
    ForkingAgent,
    SimilarityAgent,
    CloneIntelligenceAgent,
    ReusabilityAgent,
)

# Deployment layer
from agents.deployment.deployment_agents import (
    DeploymentSupervisorAgent,
    HealthMonitorAgent,
    IncidentAgent,
)

# Support layer
from agents.support.support_agents import (
    TicketTriageAgent,
    EscalationAgent,
    CustomerSuccessAgent,
)

AGENT_REGISTRY: Dict[str, Type[BaseAgent]] = {
    # Pipeline
    "IntakeAgent": IntakeAgent,
    "RequirementParserAgent": RequirementParserAgent,
    "EmbeddingAgent": EmbeddingAgent,
    "SemanticSearchAgent": SemanticSearchAgent,
    "ContextCompressionAgent": ContextCompressionAgent,
    "RankingAgent": RankingAgent,
    # Discovery
    "ReflectionAgent": ReflectionAgent,
    "MarketIntelligenceAgent": MarketIntelligenceAgent,
    # Trust
    "TrustAuditorAgent": TrustAuditorAgent,
    "FraudAgent": FraudAgent,
    "ComplianceAgent": ComplianceAgent,
    "ReputationAgent": ReputationAgent,
    # Commercial
    "CommercializationAgent": CommercializationAgent,
    "ROIAgent": ROIAgent,
    "PricingAgent": PricingAgent,
    "AcquisitionAdvisorAgent": AcquisitionAdvisorAgent,
    # Vision
    "UIAuditAgent": UIAuditAgent,
    "UXAuditAgent": UXAuditAgent,
    "ArchitectureExplanationAgent": ArchitectureExplanationAgent,
    "SecurityAuditAgent": SecurityAuditAgent,
    # Forking
    "ForkingAgent": ForkingAgent,
    "SimilarityAgent": SimilarityAgent,
    "CloneIntelligenceAgent": CloneIntelligenceAgent,
    "ReusabilityAgent": ReusabilityAgent,
    # Deployment
    "DeploymentSupervisorAgent": DeploymentSupervisorAgent,
    "HealthMonitorAgent": HealthMonitorAgent,
    "IncidentAgent": IncidentAgent,
    # Support
    "TicketTriageAgent": TicketTriageAgent,
    "EscalationAgent": EscalationAgent,
    "CustomerSuccessAgent": CustomerSuccessAgent,
}


def get_agent(name: str) -> BaseAgent:
    """Instantiate an agent by name."""
    cls = AGENT_REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Unknown agent: {name}. Available: {list(AGENT_REGISTRY.keys())}")
    return cls()


AGENT_NAMES = list(AGENT_REGISTRY.keys())
TOTAL_AGENTS = len(AGENT_REGISTRY)  # 28
