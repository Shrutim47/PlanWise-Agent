import pytest

from app import build_event_payload, run_event_plan
from src.agents import build_budget_agent, build_planner_agent, build_vendor_agent
from src.crew import PlanWiseCrew, create_planwise_crew
from src.tasks import build_event_tasks


def test_agents_are_created_with_expected_roles():
    planner = build_planner_agent()
    vendor = build_vendor_agent()
    budget = build_budget_agent()

    assert planner.role == "Event Planning Lead"
    assert vendor.role == "Venue & Vendor Researcher"
    assert budget.role == "Budget & Risk Analyst"


def test_event_tasks_are_built_with_three_steps():
    planner = build_planner_agent()
    vendor = build_vendor_agent()
    budget = build_budget_agent()

    tasks = build_event_tasks(planner, vendor, budget)

    assert len(tasks) == 3
    assert {task.name for task in tasks} == {
        "event_research",
        "budget_analysis",
        "final_plan",
    }


def test_crew_is_created_with_agents_and_tasks():
    crew = create_planwise_crew()

    assert isinstance(crew, PlanWiseCrew)
    assert len(crew.agents) == 3
    assert len(crew.tasks) == 3
    assert crew.name == "PlanWise Crew"


def test_event_payload_builder_and_offline_plan_generation():
    payload = build_event_payload(
        event_name="Q4 Kickoff",
        event_type="conference",
        preferred_location="Bengaluru",
        estimated_attendance=200,
        total_budget=600000,
        venue_type="garden terrace",
        weather_forecast="rain showers",
    )

    result = run_event_plan(**payload)

    assert payload["event_name"] == "Q4 Kickoff"
    assert result["estimated_attendance"] == 200
    assert result["budget_summary"]["total_budget"] == 600000
    assert result["weather_risk"]["status"] == "warning"
    assert "vendor_shortlist" in result


def test_pune_event_returns_real_vendor_shortlist_and_selected_venue():
    payload = build_event_payload(
        event_name="Leadership Meetup",
        event_type="conference",
        preferred_location="Pune",
        estimated_attendance=200,
        total_budget=600000,
        venue_type="outdoor garden",
        weather_forecast="clear",
    )

    result = run_event_plan(**payload)

    shortlist = result.get("vendor_shortlist", [])
    selected = result.get("selected_venue", {})

    assert shortlist, "Expected at least one venue recommendation in the shortlist."
    assert selected.get("name") != "No catalog match found"
    assert selected.get("location", "").lower() == "pune"
    assert any(item.get("category") == "venues" for item in shortlist)
    assert any(item.get("category") == "caterers" for item in shortlist)
    assert any(item.get("category") == "av_rentals" for item in shortlist)


def test_event_type_routes_occasion_fit_and_catering_menu_within_city():
    planner = create_planwise_crew()
    expected_labels = {
        "birthday": "🎉 Best for Birthdays",
        "leadership summit": "💼 Tailored for Corporate Summits",
        "college tech fest": "⚡ Built for Tech Fests",
    }

    for event_type, expected_label in expected_labels.items():
        result = planner._offline_kickoff(
            {
                "event_name": "Occasion routing regression",
                "event_type": event_type,
                "preferred_location": "Pune",
                "estimated_attendance": 180,
                "total_budget": 600000,
                "venue_type": "indoor hall",
                "weather_forecast": "clear",
            }
        )

        assert result["recommended_venues"][0]["occasion_fit"] == expected_label
        assert result["recommended_caterers"][0]["menu_recommendation"]
        assert all(
            vendor["location"] == "Pune"
            for vendor in (
                result["recommended_venues"]
                + result["recommended_caterers"]
                + result["recommended_av_vendors"]
            )
        )
