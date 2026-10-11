from __future__ import annotations

import os

from crewai import Agent

from src.tools import (
    budget_calculator_tool,
    check_weather_risk_tool,
    vendor_search_tool,
    verify_budget_ceiling_tool,
    verify_venue_capacity_tool,
)


def _resolve_llm() -> str | None:
    """Prefer an explicit model setting but gracefully fall back to the OpenAI default."""
    configured_model = os.getenv("PLANWISE_LLM") or os.getenv("OPENAI_MODEL") or os.getenv("MODEL_NAME")
    if configured_model:
        return configured_model
    if os.getenv("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    return None


def build_planner_agent() -> Agent:
    """Create the event-planning lead responsible for synthesis and final recommendations."""
    return Agent(
        role="Event Planning Lead",
        goal="Convert the event brief into a practical event plan grounded in vendor fit, budget feasibility, and risk awareness.",
        backstory=(
            "You are the lead planner for PlanWise. You translate a brief into a feasible, "
            "well-justified event strategy using vendor research, budget boundaries, and risk checks."
        ),
        llm=_resolve_llm(),
        verbose=True,
        allow_delegation=True,
        tools=[],
    )


def build_vendor_agent() -> Agent:
    """Create the researcher that finds venues, caterers, and AV partners from the catalog."""
    return Agent(
        role="Venue & Vendor Researcher",
        goal="Recommend credible venue, catering, and AV options within the event budget and attendance target.",
        backstory=(
            "You are the sourcing expert for PlanWise. You search the local vendor catalog and pull "
            "the most relevant venue and service recommendations based on capacity, location, and cost."
        ),
        llm=_resolve_llm(),
        verbose=True,
        allow_delegation=False,
        tools=[vendor_search_tool],
    )


def build_budget_agent() -> Agent:
    """Create the analyst responsible for budget validation and risk checks."""
    return Agent(
        role="Budget & Risk Analyst",
        goal="Validate spending against the event budget, check capacity fit, and flag weather or cost risks before final approval.",
        backstory=(
            "You are the budget and risk analyst for PlanWise. You ensure cost control, venue suitability, "
            "and weather resilience before the plan can be approved."
        ),
        llm=_resolve_llm(),
        verbose=True,
        allow_delegation=False,
        tools=[
            budget_calculator_tool,
            verify_budget_ceiling_tool,
            verify_venue_capacity_tool,
            check_weather_risk_tool,
        ],
    )


__all__ = [
    "build_planner_agent",
    "build_vendor_agent",
    "build_budget_agent",
]
