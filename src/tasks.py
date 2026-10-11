from __future__ import annotations

from typing import List

from crewai import Task

from src.agents import build_budget_agent, build_planner_agent, build_vendor_agent


def build_event_tasks(
    planner_agent=None,
    vendor_agent=None,
    budget_agent=None,
) -> List[Task]:
    """Build the sequential event-planning workflow for the PlanWise crew."""
    planning_agent = planner_agent or build_planner_agent()
    research_agent = vendor_agent or build_vendor_agent()
    budgeting_agent = budget_agent or build_budget_agent()

    event_research = Task(
        name="event_research",
        description=(
            "Research venues, caterers, and AV vendors for the {event_type} event in {preferred_location} using the local vendor catalog. "
            "Pass event_type, city, budget, and attendee_count to vendor search. Respect the city boundary strictly, "
            "rank venues by occasion fit, and align catering menus with the event vibe."
        ),
        expected_output=(
            "A list of 3 to 5 candidate vendors or venues with category, occasion fit, vibe, capacity, budget position, "
            "and a short match explanation. Include an occasion-aligned caterer menu."
        ),
        agent=research_agent,
    )

    budget_analysis = Task(
        name="budget_analysis",
        description=(
            "Calculate the fixed budget split and validate the chosen plan against the total budget, attendee count, "
            "and venue capacity. Flag any weather-related risks for outdoor venues."
        ),
        expected_output=(
            "A validated budget summary showing allocations, total spend, capacity fit, and any safety or risk notes."
        ),
        agent=budgeting_agent,
        context=[event_research],
    )

    final_plan = Task(
        name="final_plan",
        description=(
            "Combine the best vendor options and the verified budget to produce a final event recommendation with "
            "clear next steps and decision rationale."
        ),
        expected_output=(
            "A concise final recommended event plan covering venue choice, budget summary, vendor shortlist, and all key risks."
        ),
        agent=planning_agent,
        context=[event_research, budget_analysis],
    )

    return [event_research, budget_analysis, final_plan]


__all__ = ["build_event_tasks"]
