from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict

import requests


logger = logging.getLogger(__name__)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 5


def _weather_description(code: int) -> str:
    if code == 0:
        return "clear"
    if code in {1, 2}:
        return "partly cloudy"
    if code == 3:
        return "overcast"
    if code in {45, 48}:
        return "foggy"
    if code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67}:
        return "rain showers"
    if code in {80, 81, 82}:
        return "rain showers"
    if code in {71, 73, 75, 77, 85, 86}:
        return "snow"
    if code in {95, 96, 99}:
        return "thunderstorms"
    return "variable conditions"


def get_weather_forecast(city: str, forecast_date: date | datetime | str) -> Dict[str, Any] | None:
    """Fetch an Open-Meteo daily forecast, returning None when unavailable."""
    try:
        if isinstance(forecast_date, datetime):
            requested_date = forecast_date.date().isoformat()
        elif isinstance(forecast_date, date):
            requested_date = forecast_date.isoformat()
        else:
            requested_date = date.fromisoformat(str(forecast_date)).isoformat()

        location_response = requests.get(
            GEOCODING_URL,
            params={"name": str(city).strip(), "count": 1, "language": "en", "format": "json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        location_response.raise_for_status()
        locations = location_response.json().get("results") or []
        if not locations:
            return None
        location = locations[0]

        forecast_response = requests.get(
            FORECAST_URL,
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "daily": "weather_code,temperature_2m_max,precipitation_probability_max",
                "start_date": requested_date,
                "end_date": requested_date,
                "timezone": "auto",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        forecast_response.raise_for_status()
        daily = forecast_response.json().get("daily") or {}
        dates = daily.get("time") or []
        if requested_date not in dates:
            return None

        index = dates.index(requested_date)
        weather_code = daily.get("weather_code", [])[index]
        temperature = daily.get("temperature_2m_max", [])[index]
        rain_probability = daily.get("precipitation_probability_max", [])[index]
        if temperature is None or rain_probability is None:
            return None

        return {
            "summary": _weather_description(int(weather_code)),
            "temperature_c": float(temperature),
            "rain_probability": int(rain_probability),
            "date": requested_date,
            "location_name": location.get("name", str(city).strip()),
            "source": "Open-Meteo",
        }
    except Exception as exc:
        logger.warning("Open-Meteo forecast unavailable for %s on %s: %s", city, forecast_date, exc)
        return None