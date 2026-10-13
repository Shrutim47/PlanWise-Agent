from __future__ import annotations

from datetime import date
from typing import Any, Dict
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

from src.crew import create_planwise_crew
from src.tools.rag_tool import search_geoapify_vendors, using_sample_catalog
from src.weather import get_weather_forecast


def _money(value: Any) -> str:
    """Format a numeric value as Indian Rupee currency."""
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₹0.00"


def _vendor_website(vendor: Dict[str, Any], fallback_terms: str) -> str:
    website = str(vendor.get("website") or "").strip()
    if website.startswith(("https://", "http://")):
        return website
    return f"https://www.google.com/search?q={quote_plus(fallback_terms)}"


def _merge_live_vendors(catalog_vendors: list[Dict[str, Any]], live_vendors: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    live_ids = {str(vendor.get("id")) for vendor in live_vendors if vendor.get("id")}
    catalog_remaining = [vendor for vendor in catalog_vendors if str(vendor.get("id")) not in live_ids]
    return live_vendors + catalog_remaining


def build_event_payload(
    event_name: str,
    event_type: str,
    preferred_location: str,
    estimated_attendance: int,
    total_budget: float,
    venue_type: str,
    weather_forecast: str,
) -> Dict[str, Any]:
    """Normalise a form submission into the event-planning payload expected by the crew."""
    return {
        "event_name": event_name or "PlanWise Event",
        "event_type": event_type or "corporate gathering",
        "preferred_location": preferred_location or "Bengaluru",
        "estimated_attendance": int(estimated_attendance or 0),
        "total_budget": float(total_budget or 0),
        "venue_type": venue_type or "outdoor garden",
        "weather_forecast": weather_forecast or "clear",
    }


def run_event_plan(**kwargs: Any) -> Dict[str, Any]:
    """Execute the deterministic PlanWise planning workflow and return a structured result."""
    crew = create_planwise_crew()
    return crew.kickoff(**kwargs)


def render_event_dashboard(result: Dict[str, Any]) -> None:
    """Render the event-planning dashboard using safe dictionary lookups."""
    if not isinstance(result, dict):
        st.warning("No result payload was returned from the planner.")
        return

    budget_summary = result.get("budget_summary", {}) if isinstance(result.get("budget_summary", {}), dict) else {}
    breakdown = budget_summary.get("breakdown", {}) if isinstance(budget_summary.get("breakdown", {}), dict) else {}
    weather_risk = result.get("weather_risk", {}) if isinstance(result.get("weather_risk", {}), dict) else {}
    selected_venue = result.get("selected_venue", {}) if isinstance(result.get("selected_venue", {}), dict) else {}
    recommended_venues = result.get("recommended_venues", []) if isinstance(result.get("recommended_venues", []), list) else []
    if not recommended_venues and isinstance(result.get("vendor_shortlist", []), list):
        recommended_venues = [
            vendor for vendor in result.get("vendor_shortlist", [])
            if isinstance(vendor, dict) and vendor.get("category") == "venues"
        ]
    recommended_caterers = result.get("recommended_caterers", []) if isinstance(result.get("recommended_caterers", []), list) else []
    recommended_av_vendors = result.get("recommended_av_vendors", []) if isinstance(result.get("recommended_av_vendors", []), list) else []

    total_budget = float(result.get("total_budget", 0.0) or 0.0)
    estimated_attendance = int(result.get("estimated_attendance", 0) or 0)
    per_head_allowance = float(budget_summary.get("per_head_catering_allowance", 0.0) or 0.0)
    venue_budget = float(result.get("venue_budget", 0.0) or 0.0)
    weather_status = str(weather_risk.get("status", "ok")).strip().upper() or "OK"
    food_warning = bool(budget_summary.get("food_budget_warning", False))
    user_location = str(result.get("preferred_location") or "Your location").strip() or "Your location"
    user_event_type = str(result.get("event_type") or "event").strip() or "event"
    forecast_temperature = result.get("weather_temperature_c")
    rain_probability = result.get("rain_probability")

    st.subheader("Recommended event plan")
    metric_cols = st.columns(6)
    metric_cols[0].metric("Total Budget", _money(total_budget))
    metric_cols[1].metric("Estimated Attendance", f"{estimated_attendance} guests")
    metric_cols[2].metric("Per-Head Catering", _money(per_head_allowance))
    metric_cols[3].metric(
        "Forecast Temperature",
        f"{float(forecast_temperature):.1f} °C" if forecast_temperature is not None else "N/A",
    )
    metric_cols[4].metric(
        "Rain Probability",
        f"{int(rain_probability)}%" if rain_probability is not None else "N/A",
    )

    if weather_status == "WARNING":
        metric_cols[5].markdown(
            "<div style='background:#fff3cd; color:#856404; padding:10px; border-radius:8px; text-align:center; font-weight:600;'>⚠️ WEATHER RISK</div>",
            unsafe_allow_html=True,
        )
    else:
        metric_cols[5].markdown(
            "<div style='background:#d4edda; color:#155724; padding:10px; border-radius:8px; text-align:center; font-weight:600;'>✅ WEATHER OK</div>",
            unsafe_allow_html=True,
        )

    summary_tab, budget_tab, vendor_tab, risk_tab = st.tabs([
        "📌 Executive Summary",
        "💰 Budget Breakdown",
        "🏢 Matched Vendors",
        "🛡️ Safety & Risk Assessment",
    ])

    with summary_tab:
        st.write(f"**Event Name:** {result.get('event_name', 'N/A')}")
        st.write(f"**Event Type:** {result.get('event_type', 'N/A')}")
        st.write(f"**Target City:** {result.get('preferred_location', 'N/A')}")
        st.write(f"**Event Date:** {result.get('event_date', 'N/A')}")
        st.write(f"**Weather Source:** {result.get('weather_source', 'Manual fallback')}")
        st.write(f"**Recommendation:** {result.get('recommendation', 'No recommendation available.')}")

    with budget_tab:
        budget_frame = pd.DataFrame(
            [
                {
                    "Allocation": "Venue",
                    "Share": "30%",
                    "Amount": breakdown.get("venue", 0.0),
                },
                {
                    "Allocation": "Catering",
                    "Share": "40%",
                    "Amount": breakdown.get("catering", 0.0),
                },
                {
                    "Allocation": "AV Equipment",
                    "Share": "15%",
                    "Amount": breakdown.get("av_equipment", 0.0),
                },
                {
                    "Allocation": "Contingency Buffer",
                    "Share": "15%",
                    "Amount": breakdown.get("contingency_buffer", 0.0),
                },
            ]
        )
        budget_frame["Amount"] = budget_frame["Amount"].apply(lambda value: float(value) if isinstance(value, (int, float)) else 0.0)
        st.table(budget_frame.style.format({"Amount": _money}))

        if food_warning:
            st.error(
                budget_summary.get(
                    "food_budget_warning_message",
                    "Per-head catering allocation is below the recommended threshold.",
                )
            )
        else:
            st.success(
                budget_summary.get(
                    "food_budget_warning_message",
                    "Per-head catering allowance is within the recommended threshold.",
                )
            )

    with vendor_tab:
        st.caption("Live place data, when available: © OpenStreetMap contributors via Geoapify.")
        if not recommended_venues:
            st.info(f"No venues exist in {user_location} yet in the catalog, so this view is intentionally showing no cross-city matches.")
        else:
            venue_columns = st.columns(min(len(recommended_venues), 3))
            for index, venue in enumerate(recommended_venues[:3]):
                with venue_columns[index]:
                    venue_name = str(venue.get("name") or "Venue recommendation")
                    locality = str(venue.get("locality") or venue.get("location") or "Unknown")
                    city = str(venue.get("location") or "Unknown")
                    is_live = venue.get("source") == "geoapify"
                    daily_rate = venue.get("cost_per_day")
                    capacity = venue.get("capacity")
                    venue_type = str(venue.get("type") or "Unknown").title()
                    rating = venue.get("rating")
                    amenities = venue.get("amenities", []) if isinstance(venue.get("amenities", []), list) else []
                    contact = str(venue.get("contact") or "Not provided")
                    match_label = str(venue.get("match_label") or "Recommended")
                    occasion_fit = str(venue.get("occasion_fit") or match_label)
                    vibe = str(venue.get("vibe") or "Versatile / Event-ready setup")
                    badge_text = f"📍 {locality}, {city}"
                    comparison = (
                        "Live listing · confirm pricing"
                        if is_live
                        else "Under venue budget" if float(daily_rate or 0.0) <= venue_budget else "Above venue budget"
                    )
                    website = _vendor_website(venue, f"{venue_name} {locality}")

                    with st.container(border=True):
                        st.caption(badge_text)
                        st.subheader(venue_name)
                        if is_live:
                            st.caption("Live data (OpenStreetMap via Geoapify)")
                        st.write(f"{locality}, {city}")
                        st.badge(occasion_fit)
                        st.badge(comparison)
                        st.caption(f"Retrieval: {venue.get('retrieval_method', 'rules-only')}")
                        st.write(f"**Vibe:** {vibe}")
                        if venue.get("occasion_note"):
                            st.caption(str(venue["occasion_note"]))
                        st.write(f"**Style:** {venue_type}")
                        st.write(
                            f"**Capacity:** {capacity} guests vs. target {estimated_attendance}"
                            if capacity is not None
                            else "**Capacity:** Check with vendor"
                        )
                        st.write(
                            f"**Daily rate:** {_money(daily_rate)} vs. venue budget {_money(venue_budget)}"
                            if daily_rate is not None
                            else "**Daily rate:** Check with vendor"
                        )
                        st.write(f"**Rating:** {float(rating):.1f} / 5" if rating is not None else "**Rating:** Check with vendor")
                        st.write(f"**Amenities:** {', '.join(amenities[:4]) if amenities else 'Not listed'}")
                        st.write(f"**Contact:** {contact}")
                        st.link_button("🌐 Visit Official Website" if venue.get("website") else "Search vendor online", website)

        if recommended_caterers:
            st.subheader("Recommended Caterers")
            caterer_cols = st.columns(min(len(recommended_caterers), 3))
            for index, caterer in enumerate(recommended_caterers[:3]):
                with caterer_cols[index]:
                    caterer_name = str(caterer.get("name") or "Caterer")
                    locality = str(caterer.get("locality") or caterer.get("location") or "Unknown")
                    city = str(caterer.get("location") or "Unknown")
                    cuisine = str(caterer.get("type") or "General").replace("_", " ").title()
                    event_rate = float(caterer.get("cost_per_day", 0.0) or 0.0)
                    per_plate_price = float(
                        caterer.get("cost_per_plate")
                        or (event_rate / estimated_attendance if estimated_attendance else 0.0)
                    )
                    amenities = caterer.get("amenities", [])
                    amenities = amenities if isinstance(amenities, list) else []
                    website = _vendor_website(caterer, f"{caterer_name} {locality}")
                    is_live = caterer.get("source") == "geoapify"
                    menu_recommendation = str(
                        caterer.get("menu_recommendation") or f"Menu tailored for {user_event_type}"
                    )
                    caterer_vibe = str(caterer.get("vibe") or "Flexible / Event-ready catering")

                    with st.container(border=True):
                        st.subheader(caterer_name)
                        if is_live:
                            st.caption("Live data (OpenStreetMap via Geoapify)")
                        st.caption(f"{locality}, {city}")
                        st.badge(str(caterer.get("occasion_fit") or f"Tailored for {user_event_type}"))
                        st.caption(f"Retrieval: {caterer.get('retrieval_method', 'rules-only')}")
                        st.write(f"**Recommended menu:** {menu_recommendation}")
                        st.write(f"**Vibe:** {caterer_vibe}")
                        st.write(f"**Cuisine:** {cuisine}")
                        st.write("**Per-plate price:** Check with vendor" if is_live else f"**Per-plate price:** {_money(per_plate_price)}")
                        st.write(f"**Per-head budget:** {_money(per_head_allowance)}")
                        st.write("**Estimated event rate:** Check with vendor" if is_live else f"**Estimated event rate:** {_money(event_rate)}")
                        capacity = caterer.get("capacity")
                        st.write(f"**Capacity:** {capacity} guests" if capacity is not None else "**Capacity:** Check with vendor")
                        st.write(f"**Amenities:** {', '.join(amenities[:4]) if amenities else 'Not listed'}")
                        st.write(f"**Contact:** {caterer.get('contact', 'Not provided')}")
                        st.link_button("🍽️ View Menu & Website" if caterer.get("website") else "Search caterer online", website)

        if recommended_av_vendors:
            st.subheader("Recommended AV Vendors")
            av_cols = st.columns(min(len(recommended_av_vendors), 3))
            for index, av_vendor in enumerate(recommended_av_vendors[:3]):
                with av_cols[index]:
                    st.markdown(f"**{av_vendor.get('name', 'AV Vendor')}**")
                    st.caption(f"{av_vendor.get('locality', av_vendor.get('location', 'Unknown'))}, {av_vendor.get('location', 'Unknown')}")
                    st.write(f"Daily rate: {_money(av_vendor.get('cost_per_day', 0.0))}")
                    st.write(f"Capacity: {av_vendor.get('capacity', 'N/A')} guests")
                    st.write(f"Type: {str(av_vendor.get('type', 'Unknown')).title()}")
                    st.caption(f"Retrieval: {av_vendor.get('retrieval_method', 'rules-only')}")
                    st.write(f"Contact: {av_vendor.get('contact', 'Not provided')}")
                    st.link_button("Visit vendor website", _vendor_website(av_vendor, str(av_vendor.get("name", "AV vendor"))))

    with risk_tab:
        backup_required = bool(weather_risk.get("backup_required", False))
        if weather_status == "WARNING":
            st.warning(
                weather_risk.get(
                    "recommendation",
                    "Weather risk flagged; consider an indoor backup venue or weather-proof setup.",
                )
            )
        else:
            st.success(
                weather_risk.get(
                    "recommendation",
                    "No weather-related operational risk detected for the selected venue style.",
                )
            )

        st.write(f"**Weather Risk:** {weather_status}")
        st.write(f"**Backup Required:** {'Yes' if backup_required else 'No'}")
        st.write(
            f"**Contingency Plan:** {weather_risk.get('recommendation', 'No specific contingency plan provided.')}"
        )

    with st.expander("🔍 View Raw Agent JSON Payload (Debug)"):
        st.json(result)


def render_app() -> None:
    """Render the Streamlit UI for PlanWise event planning."""
    st.set_page_config(page_title="PlanWise", page_icon="📋", layout="wide")
    st.title("PlanWise Event Planner")
    st.caption("Autonomous vendor, budget, and risk planning for corporate gatherings.")
    if using_sample_catalog():
        st.info("Using sample catalogue. Recommendations use fictional demo vendor data.")

    with st.form("planwise_form"):
        col1, col2 = st.columns(2)
        with col1:
            event_name = st.text_input("Event name", value="Spring Leadership Summit")
            event_type = st.selectbox(
                "Event type",
                [
                    "corporate gathering",
                    "leadership summit",
                    "tech fest",
                    "birthday",
                    "private party",
                    "college tech fest",
                    "hackathon",
                    "conference",
                    "cultural night",
                ],
            )
            preferred_location = st.text_input("Preferred location", value="Bengaluru")
            event_date = st.date_input("Event date", value=date.today())
        with col2:
            estimated_attendance = st.number_input("Estimated attendance", min_value=10, max_value=5000, value=180)
            total_budget = st.number_input("Total budget (₹)", min_value=50000, max_value=5000000, value=500000, step=50000)
            venue_type = st.selectbox(
                "Venue style",
                ["outdoor garden", "indoor hall", "terrace", "rooftop", "beach resort"],
            )
        weather_forecast_fallback = st.text_input(
            "Fallback weather description",
            value="clear",
            help="Used for the risk check if Open-Meteo cannot provide a forecast for the selected date.",
        )

        submit = st.form_submit_button("Plan my event")

    if submit:
        payload = build_event_payload(
            event_name=event_name,
            event_type=event_type,
            preferred_location=preferred_location,
            estimated_attendance=estimated_attendance,
            total_budget=total_budget,
            venue_type=venue_type,
            weather_forecast=weather_forecast_fallback,
        )
        payload["event_date"] = event_date.isoformat()

        forecast = get_weather_forecast(preferred_location, event_date)
        if forecast is not None:
            payload["weather_forecast"] = forecast["summary"]
            payload["weather_temperature_c"] = forecast["temperature_c"]
            payload["rain_probability"] = forecast["rain_probability"]
            payload["weather_source"] = forecast["source"]
        else:
            payload["weather_source"] = "Manual fallback"
            st.warning("Forecast unavailable for this city/date. Using the fallback weather description for the risk check.")

        with st.spinner("Reviewing vendors, budget, and risk signals..."):
            result = run_event_plan(**payload)

        if isinstance(result, dict):
            live_venues = search_geoapify_vendors("venues", preferred_location)
            live_caterers = search_geoapify_vendors("caterers", preferred_location)
            catalog_venues = result.get("recommended_venues", [])
            catalog_caterers = result.get("recommended_caterers", [])
            result["recommended_venues"] = _merge_live_vendors(
                catalog_venues if isinstance(catalog_venues, list) else [], live_venues
            )
            result["recommended_caterers"] = _merge_live_vendors(
                catalog_caterers if isinstance(catalog_caterers, list) else [], live_caterers
            )
            result["vendor_shortlist"] = (
                result["recommended_venues"]
                + result["recommended_caterers"]
                + (result.get("recommended_av_vendors", []) if isinstance(result.get("recommended_av_vendors", []), list) else [])
            )

        render_event_dashboard(result)


if __name__ == "__main__":
    render_app()
