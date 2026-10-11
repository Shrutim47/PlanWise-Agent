from __future__ import annotations

import json
from typing import Any, Dict

try:
    from crewai.tools import tool
except Exception:  # pragma: no cover - safety fallback when CrewAI is absent
    def tool(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

try:
    from crewai.tools import BaseTool
except Exception:  # pragma: no cover - compatibility fallback
    class BaseTool:  # type: ignore[no-redef]
        name = "BaseTool"
        description = "Base compatibility class for tool wrappers."


def verify_budget_ceiling(total_budget: float, estimated_cost: float) -> bool:
    """Return True when cost remains within budget and raise a ValueError if it exceeds the cap."""
    if estimated_cost > total_budget:
        raise ValueError(
            f"Estimated cost ₹{estimated_cost:,.2f} exceeds the total budget of ₹{total_budget:,.2f}. "
            "Reduce scope or request a budget increase."
        )
    return True


@tool("VerifyBudgetCeilingTool")
def verify_budget_ceiling_tool(total_budget: float, estimated_cost: float) -> str:
    """Tool wrapper around the budget ceiling validation guardrail."""
    return json.dumps({"passed": verify_budget_ceiling(total_budget, estimated_cost)}, ensure_ascii=False)


class VerifyBudgetCeilingTool(BaseTool):
    name: str = "VerifyBudgetCeilingTool"
    description: str = "Ensures estimated spend remains under the total budget and raises a constraint violation when it does not."

    def _run(self, total_budget: float, estimated_cost: float) -> str:
        return json.dumps({"passed": verify_budget_ceiling(total_budget, estimated_cost)}, ensure_ascii=False)


VerifyBudgetCeilingTool.model_rebuild()


def verify_venue_capacity(attendee_count: int, venue_capacity: int) -> bool:
    """Reject a venue when its seating capacity is below the expected attendee headcount."""
    if attendee_count > venue_capacity:
        raise ValueError(
            f"Venue capacity {venue_capacity} is below the required attendance of {attendee_count}. "
            "Choose a larger venue or reduce the guest list."
        )
    return True


@tool("VerifyVenueCapacityTool")
def verify_venue_capacity_tool(attendee_count: int, venue_capacity: int) -> str:
    """Tool wrapper around the venue capacity validation guardrail."""
    return json.dumps({"passed": verify_venue_capacity(attendee_count, venue_capacity)}, ensure_ascii=False)


class VerifyVenueCapacityTool(BaseTool):
    name: str = "VerifyVenueCapacityTool"
    description: str = "Validates that the selected venue can accommodate the expected attendee headcount."

    def _run(self, attendee_count: int, venue_capacity: int) -> str:
        return json.dumps({"passed": verify_venue_capacity(attendee_count, venue_capacity)}, ensure_ascii=False)


VerifyVenueCapacityTool.model_rebuild()


def check_weather_risk(venue_type: str, weather_forecast: str) -> Dict[str, Any]:
    """Warn when an outdoor venue is at risk from rain, recommending an indoor backup venue."""
    normalized_venue = str(venue_type or "").strip().lower().replace("_", " ")
    normalized_weather = str(weather_forecast or "").strip().lower()

    outdoor_types = {"outdoor", "garden", "terrace", "rooftop", "beach", "courtyard", "pavilion"}
    rainy_terms = {"rain", "rainy", "showers", "storm", "thunderstorm", "downpour", "wet weather"}

    venue_is_outdoor = (
        "outdoor" in normalized_venue or
        any(term in normalized_venue for term in outdoor_types)
    )

    if venue_is_outdoor and any(term in normalized_weather for term in rainy_terms):
        return {
            "status": "warning",
            "backup_required": True,
            "recommendation": "Outdoor venue has rain risk. Recommend a covered indoor backup venue or a tented weather-proof option.",
        }

    return {
        "status": "ok",
        "backup_required": False,
        "recommendation": "No weather-related risk detected for the selected venue type.",
    }


@tool("CheckWeatherRiskTool")
def check_weather_risk_tool(venue_type: str, weather_forecast: str) -> str:
    """Tool wrapper around the weather-risk guardrail."""
    return json.dumps(check_weather_risk(venue_type, weather_forecast), ensure_ascii=False)


class CheckWeatherRiskTool(BaseTool):
    name: str = "CheckWeatherRiskTool"
    description: str = "Checks whether an outdoor venue is exposed to a weather emergency and suggests backup options."

    def _run(self, venue_type: str, weather_forecast: str) -> str:
        return json.dumps(check_weather_risk(venue_type, weather_forecast), ensure_ascii=False)


CheckWeatherRiskTool.model_rebuild()
