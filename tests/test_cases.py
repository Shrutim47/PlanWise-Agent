import json
from datetime import date
from unittest.mock import Mock

import pytest

from app import build_event_payload, run_event_plan
from src.agents import build_budget_agent, build_planner_agent, build_vendor_agent
from src.crew import PlanWiseCrew, create_planwise_crew
from src.tasks import build_event_tasks
from src.tools import rag_tool
from src.tools.budget_tool import calculate_budget_breakdown
from src.tools.guardrails import check_weather_risk, verify_budget_ceiling, verify_venue_capacity
from src import weather


@pytest.fixture(autouse=True)
def use_isolated_sample_catalog(monkeypatch, tmp_path):
    """Use fictional sample data and a temporary Chroma store for offline tests."""
    sample_path = rag_tool.PROJECT_ROOT / "data" / "sample_vendor_catalog.json"
    monkeypatch.setattr(rag_tool, "DEFAULT_CATALOG_PATH", tmp_path / "vendor_catalog.json")
    monkeypatch.setattr(rag_tool, "SAMPLE_CATALOG_PATH", sample_path)
    monkeypatch.setattr(rag_tool, "DEFAULT_DB_PATH", tmp_path / "chroma_db")


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
    """Occasion routing selects matching venues and menus without crossing cities."""
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


def test_budget_overrun_rejected_and_exact_ceiling_passes():
    """Budget validation rejects an overrun but accepts a cost equal to the cap."""
    with pytest.raises(ValueError):
        verify_budget_ceiling(1000, 1000.01)
    assert verify_budget_ceiling(1000, 1000) is True


def test_capacity_mismatch_rejected_and_exact_capacity_passes():
    """Capacity validation rejects excess attendees and accepts an exact fit."""
    with pytest.raises(ValueError):
        verify_venue_capacity(101, 100)
    assert verify_venue_capacity(100, 100) is True


def test_food_allowance_threshold_and_invalid_inputs():
    """Food allowance warns below Rs. 150, not at the boundary, and rejects invalid inputs."""
    assert calculate_budget_breakdown(372.5, 1)["food_budget_warning"] is True
    boundary = calculate_budget_breakdown(375, 1)
    assert boundary["per_head_catering_allowance"] == 150
    assert boundary["food_budget_warning"] is False

    for budget in (0, -1):
        with pytest.raises(ValueError):
            calculate_budget_breakdown(budget, 1)
    for attendees in (0, -1):
        with pytest.raises(ValueError):
            calculate_budget_breakdown(1000, attendees)


def test_weather_risk_outdoor_rain_and_safe_conditions():
    """Rain on an outdoor venue requires backup; indoor rain and outdoor sun are OK."""
    rainy_outdoor = check_weather_risk("outdoor garden", "rain showers")
    assert rainy_outdoor["status"] == "warning"
    assert rainy_outdoor["backup_required"] is True

    rainy_indoor = check_weather_risk("indoor hall", "rain showers")
    assert rainy_indoor["status"] == "ok"
    assert rainy_indoor["backup_required"] is False

    sunny_outdoor = check_weather_risk("outdoor lawn", "sunny")
    assert sunny_outdoor["status"] == "ok"
    assert sunny_outdoor["backup_required"] is False


def test_open_meteo_forecast_returns_condition_temperature_and_rain(monkeypatch):
    """A mocked geocode and daily forecast returns normalized weather fields."""
    geocode_response = Mock()
    geocode_response.json.return_value = {
        "results": [{"name": "Pune", "latitude": 18.52, "longitude": 73.86}]
    }
    forecast_response = Mock()
    forecast_response.json.return_value = {
        "daily": {
            "time": ["2026-10-14"],
            "weather_code": [80],
            "temperature_2m_max": [27.4],
            "precipitation_probability_max": [65],
        }
    }
    monkeypatch.setattr(weather.requests, "get", Mock(side_effect=[geocode_response, forecast_response]))

    result = weather.get_weather_forecast("Pune", date(2026, 10, 14))

    assert result == {
        "summary": "rain showers",
        "temperature_c": 27.4,
        "rain_probability": 65,
        "date": "2026-10-14",
        "location_name": "Pune",
        "source": "Open-Meteo",
    }
    assert forecast_response.raise_for_status.called


def test_open_meteo_forecast_returns_none_when_date_is_out_of_range(monkeypatch):
    """A forecast response without the requested date signals manual fallback."""
    geocode_response = Mock()
    geocode_response.json.return_value = {
        "results": [{"name": "Pune", "latitude": 18.52, "longitude": 73.86}]
    }
    forecast_response = Mock()
    forecast_response.json.return_value = {"daily": {"time": [], "weather_code": []}}
    monkeypatch.setattr(weather.requests, "get", Mock(side_effect=[geocode_response, forecast_response]))

    assert weather.get_weather_forecast("Pune", date(2035, 1, 1)) is None


def test_open_meteo_timeout_returns_none_without_crashing(monkeypatch):
    """Network timeouts are handled as unavailable forecasts for UI fallback."""
    monkeypatch.setattr(weather.requests, "get", Mock(side_effect=weather.requests.Timeout("timed out")))

    assert weather.get_weather_forecast("Pune", date(2026, 10, 14)) is None


def test_city_isolation_for_all_search_categories():
    """Each catalog search returns only the requested city and unknown cities stay empty."""
    cities = ("Pune", "Bengaluru", "Mumbai", "Delhi")
    for city in cities:
        results = (
            rag_tool.search_venues(city, 1_000_000, 75, event_type="birthday")
            + rag_tool.search_caterers(city, 1_000_000, 75, event_type="birthday")
            + rag_tool.search_av_rentals(city, 1_000_000, 75, event_type="birthday")
        )
        assert results
        assert all(record["location"] == city for record in results)

    assert rag_tool.search_venues("Atlantis", 1_000_000, 50) == []
    assert rag_tool.search_caterers("Atlantis", 1_000_000, 50) == []
    assert rag_tool.search_av_rentals("Atlantis", 1_000_000, 50) == []


def test_vector_retrieval_applies_city_category_and_capacity_filters(tmp_path):
    """Persistent Chroma results obey exact city/category and minimum-capacity filters."""
    sample_path = rag_tool.SAMPLE_CATALOG_PATH
    db_dir = tmp_path / "vector-index"
    assert rag_tool.build_vector_index(catalog_path=sample_path, db_dir=db_dir) is True

    results = rag_tool.semantic_search(
        query="technology hackathon high speed Wi-Fi stage",
        category="venues",
        city="Pune",
        attendee_count=200,
        n_results=20,
        db_dir=db_dir,
    )
    assert results
    assert all(record["category"] == "venues" for record in results)
    assert all(record["location"] == "Pune" for record in results)
    assert all(record["capacity"] >= 200 for record in results)
    assert all("similarity_distance" in record for record in results)
    assert all(record["retrieval_method"] == "vector+rules" for record in results)


def test_chroma_failure_falls_back_to_rules_only(monkeypatch):
    """A Chroma exception is logged and JSON search still returns rules-only results."""
    class BrokenChroma:
        @staticmethod
        def PersistentClient(**kwargs):
            raise RuntimeError("simulated local Chroma failure")

    monkeypatch.setattr(rag_tool, "chromadb", BrokenChroma)
    results = rag_tool.search_venues("Pune", 1_000_000, 75, event_type="birthday")
    assert results
    assert all(result["retrieval_method"] == "rules-only" for result in results)


def test_missing_private_catalog_loads_fictional_sample(caplog):
    """When the private catalog is absent, the loader selects the bundled fictional sample."""
    records = rag_tool.load_vendor_catalog()
    assert rag_tool.using_sample_catalog() is True
    assert len(records) == 40
    assert all(record["name"].startswith("Demo ") for record in records)
    required_fields = {
        "id", "name", "category", "location", "locality", "capacity", "cost_per_day",
        "type", "rating", "amenities", "description", "tags", "search_text", "website",
        "contact", "suitable_for", "vibe", "menu_recommendations",
    }
    payload = rag_tool.SAMPLE_CATALOG_PATH.read_text(encoding="utf-8")
    raw_records = json.loads(payload)["vendors"]
    assert all(required_fields <= set(record) for record in raw_records)
    for city in ("Pune", "Bengaluru", "Mumbai", "Delhi"):
        for category, minimum_count in (("venues", 4), ("caterers", 3), ("av_rentals", 3)):
            assert sum(record["location"] == city and record["category"] == category for record in raw_records) >= minimum_count
    assert all(record["contact"] == "+91-00000-00000 | demo@example.com" for record in raw_records)
    assert all(record["website"].startswith("https://example.com/demo-") for record in raw_records)
    caterers = [record for record in raw_records if record["category"] == "caterers"]
    assert all({"birthday", "corporate", "tech_fest"} <= set(record["menu_recommendations"]) for record in caterers)
    assert "using fictional sample catalog" in caplog.text
