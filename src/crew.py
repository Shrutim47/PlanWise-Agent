from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from crewai import Crew
from crewai.process import Process

from src.agents import build_budget_agent, build_planner_agent, build_vendor_agent
from src.tasks import build_event_tasks
from src.tools.budget_tool import calculate_budget_breakdown
from src.tools.guardrails import check_weather_risk, verify_budget_ceiling, verify_venue_capacity
from src.tools.rag_tool import search_av_rentals, search_caterers, search_venues


@dataclass
class PlanWiseCrew:
    """Container object for the PlanWise multi-agent planning flow."""

    name: str = "PlanWise Crew"
    agents: List[Any] = field(default_factory=list)
    tasks: List[Any] = field(default_factory=list)
    crew: Optional[Crew] = None

    def __post_init__(self) -> None:
        if not self.agents:
            planner = build_planner_agent()
            vendor = build_vendor_agent()
            budget = build_budget_agent()
            self.agents = [planner, vendor, budget]

        if not self.tasks:
            planner = next((agent for agent in self.agents if getattr(agent, "role", "") == "Event Planning Lead"), build_planner_agent())
            vendor = next((agent for agent in self.agents if getattr(agent, "role", "") == "Venue & Vendor Researcher"), build_vendor_agent())
            budget = next((agent for agent in self.agents if getattr(agent, "role", "") == "Budget & Risk Analyst"), build_budget_agent())
            self.tasks = build_event_tasks(planner, vendor, budget)

        if self.crew is None:
            self.crew = Crew(
                name=self.name,
                agents=self.agents,
                tasks=self.tasks,
                process=Process.sequential,
                verbose=True,
            )

    def _offline_kickoff(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic local planning fallback when no LLM backend is configured."""
        attendee_count = int(payload.get("estimated_attendance") or 0)
        total_budget = float(payload.get("total_budget") or 0)
        venue_type = str(payload.get("venue_type") or "outdoor garden")
        event_type = str(payload.get("event_type") or "corporate gathering")
        weather_forecast = str(payload.get("weather_forecast") or "clear")
        location = str(payload.get("preferred_location") or "Bengaluru")

        budget_summary = calculate_budget_breakdown(total_budget, attendee_count)
        venue_budget = float(budget_summary.get("breakdown", {}).get("venue", total_budget * 0.30) or 0.0)
        per_head_allowance = float(budget_summary.get("per_head_catering_allowance", 0.0) or 0.0)
        av_budget = float(budget_summary.get("breakdown", {}).get("av_equipment", total_budget * 0.15) or 0.0)

        recommended_venues = search_venues(
            location=location,
            max_venue_budget=venue_budget,
            attendee_count=attendee_count,
            venue_style=venue_type,
            limit=3,
            event_type=event_type,
        )

        selected_venue = recommended_venues[0] if recommended_venues else {
            "name": "No catalog match found",
            "capacity": attendee_count,
            "cost_per_day": venue_budget,
            "location": location,
            "locality": "Unknown",
            "type": venue_type,
            "rating": 0.0,
            "amenities": [],
            "contact": "Not provided",
        }

        recommended_caterers = search_caterers(
            location=location,
            max_caterer_budget=max(per_head_allowance * attendee_count, 0.0),
            attendee_count=attendee_count,
            limit=3,
            event_type=event_type,
        )
        recommended_av_vendors = search_av_rentals(
            location=location,
            max_av_budget=av_budget,
            attendee_count=attendee_count,
            limit=3,
            event_type=event_type,
        )

        try:
            verify_budget_ceiling(total_budget, budget_summary["total_allocated"])
            verify_venue_capacity(attendee_count, int(selected_venue.get("capacity") or attendee_count))
        except ValueError as exc:
            budget_summary["budget_guardrail_error"] = str(exc)

        weather_status = check_weather_risk(venue_type, weather_forecast)
        primary_recommendation = (
            selected_venue.get("name") if selected_venue.get("name") != "No catalog match found" else "No exact venue match found; closest catalog alternatives are recommended."
        )

        final_plan = {
            "event_name": payload.get("event_name", "PlanWise Event"),
            "event_type": payload.get("event_type", "corporate gathering"),
            "preferred_location": location,
            "estimated_attendance": attendee_count,
            "total_budget": total_budget,
            "venue_budget": venue_budget,
            "budget_summary": budget_summary,
            "recommended_venues": recommended_venues,
            "vendor_shortlist": recommended_venues + recommended_caterers + recommended_av_vendors,
            "selected_venue": selected_venue,
            "recommended_caterers": recommended_caterers,
            "recommended_av_vendors": recommended_av_vendors,
            "weather_risk": weather_status,
            "event_date": payload.get("event_date"),
            "weather_temperature_c": payload.get("weather_temperature_c"),
            "rain_probability": payload.get("rain_probability"),
            "weather_source": payload.get("weather_source", "Manual fallback"),
            "recommendation": (
                f"Primary recommendation: {primary_recommendation}. Review the ranked venue options and the cost trade-offs before final approval."
            ),
        }
        return final_plan

    def kickoff(self, **inputs: Any) -> Any:
        """Run the crew with a set of event planning inputs."""
        payload: Dict[str, Any] = {
            "event_name": "PlanWise Event",
            "event_type": "corporate gathering",
            "estimated_attendance": 150,
            "total_budget": 500000,
            "preferred_location": "Bengaluru",
            "venue_type": "outdoor garden",
            "weather_forecast": "rain showers",
        }
        payload.update(inputs)

        if not self.crew:
            return self._offline_kickoff(payload)

        try:
            return self.crew.kickoff(inputs=payload)
        except Exception:
            return self._offline_kickoff(payload)


def create_planwise_crew() -> PlanWiseCrew:
    """Create the default PlanWise event planning crew."""
    return PlanWiseCrew()


__all__ = ["PlanWiseCrew", "create_planwise_crew"]
