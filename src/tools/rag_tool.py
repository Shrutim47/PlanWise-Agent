from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import chromadb
except Exception:  # pragma: no cover - handled at runtime when dependency is missing
    chromadb = None

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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "data" / "vendor_catalog.json"
DEFAULT_DB_PATH = PROJECT_ROOT / ".chroma"
VALID_CATEGORIES = {"venues", "caterers", "av_rentals"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


PUNE_LOCALITIES = {
    "rahatni",
    "wakad",
    "baner",
    "hinjawadi",
    "koregaon park",
    "kothrud",
    "pimpri",
    "chinchwad",
    "pimple saudagar",
    "pimple",
    "saundagar",
    "shivaji nagar",
    "camp",
    "kharadi",
    "magarpatta",
    "viman nagar",
    "deccan",
    "hadapsar",
    "navi peth",
    "pashan",
    "aundh",
    "vishrantwadi",
    "fursungi",
    "moshi",
}

CITY_ALIASES = {
    "pune": {"pune", "pimpri chinchwad", "pimpri chinwad", "pimpri", "chinchwad"},
    "bengaluru": {"bengaluru", "bangalore"},
    "mumbai": {"mumbai", "bombay"},
    "delhi": {"delhi", "new delhi", "ncr"},
    "hyderabad": {"hyderabad"},
    "chennai": {"chennai"},
    "kolkata": {"kolkata"},
}

OCCASION_TERMS = {
    "birthday": {"birthday", "private party", "celebration", "party"},
    "corporate": {"corporate gathering", "leadership summit", "summit", "conference", "corporate"},
    "tech_fest": {"tech fest", "hackathon", "technology event", "college event"},
}

OCCASION_SEMANTICS = {
    "birthday": {"rooftop", "lounge", "party", "lawn", "clubhouse", "gaming", "celebration", "dj", "bar", "live counter", "mocktail"},
    "corporate": {"convention", "hotel", "conference", "ballroom", "auditorium", "executive", "boardroom", "formal", "projector", "stage", "wi fi", "wifi", "av"},
    "tech_fest": {"auditorium", "college", "tech", "hackathon", "coworking", "co working", "high bandwidth", "wi fi", "wifi", "dual screen", "projector", "stage", "audio"},
}


def _city_aliases(location: str) -> set[str]:
    normalized = _normalize_text(location)
    if not normalized:
        return set()
    aliases = CITY_ALIASES.get(normalized, {normalized})
    canonical = {alias.replace("-", " ") for alias in aliases}
    if normalized in {"pimpri", "chinchwad", "pimpri chinchwad", "pimpri chinwad"}:
        canonical |= {"pune", "pimpri chinchwad", "pimpri chinwad", "pimpri", "chinchwad"}
    return canonical


def _record_is_in_city(record: Dict[str, Any], requested_city: str) -> bool:
    if not requested_city:
        return True

    normalized_city = _normalize_text(requested_city)
    if not normalized_city:
        return True

    record_city = _normalize_text(record.get("location", ""))
    record_locality = _normalize_text(record.get("locality", ""))
    city_aliases = _city_aliases(normalized_city)

    if record_city in city_aliases:
        return True
    if record_locality in city_aliases:
        return True

    if normalized_city == "pune":
        if record_city == "pune" or record_locality in PUNE_LOCALITIES:
            return True
        if record_locality and any(token in record_locality for token in {"pune", "baner", "wakad", "rahatni", "hinjawadi", "koregaon", "kothrud", "pimple"}):
            return True

    if record_city and normalized_city in record_city:
        return True
    if record_locality and normalized_city in record_locality:
        return True
    return False


def _filter_records_by_city(records: List[Dict[str, Any]], location: str) -> List[Dict[str, Any]]:
    normalized = _normalize_text(location)
    if not normalized:
        return list(records)
    return [record for record in records if _record_is_in_city(record, normalized)]


def _str_or_default(value: Any, default: str = "N/A") -> str:
    text = str(value).strip() if value is not None else ""
    return text if text else default


def _normalise_vendor_record(raw_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_record, dict):
        return None

    category = str(raw_record.get("category", "")).strip().lower()
    if category not in VALID_CATEGORIES:
        return None

    location = _str_or_default(raw_record.get("location"), "Unknown")
    locality = _str_or_default(raw_record.get("locality"), location)
    amenities = raw_record.get("amenities", []) or []
    if isinstance(amenities, str):
        amenities = [amenities]
    if not isinstance(amenities, list):
        amenities = []

    type_name = str(raw_record.get("type", "generic")).strip().lower()
    if not type_name:
        type_name = "generic"

    venue = {
        "id": _str_or_default(raw_record.get("id") or raw_record.get("name") or f"{category}-{len(raw_record)}"),
        "name": _str_or_default(raw_record.get("name"), "Unnamed Vendor"),
        "category": category,
        "type": type_name,
        "location": location,
        "locality": locality,
        "capacity": _safe_int(raw_record.get("capacity"), 0),
        "cost_per_day": _safe_float(raw_record.get("cost_per_day"), 0.0),
        "rating": _safe_float(raw_record.get("rating"), 4.0),
        "description": _str_or_default(raw_record.get("description"), ""),
        "amenities": amenities,
        "contact": _str_or_default(raw_record.get("contact"), "Not provided"),
        "tags": raw_record.get("tags", []) or [],
        "search_text": _str_or_default(raw_record.get("search_text"), ""),
        "website": _str_or_default(raw_record.get("website"), ""),
        "suitable_for": raw_record.get("suitable_for", []) or [],
        "vibe": _str_or_default(raw_record.get("vibe"), "Versatile / Event-ready setup"),
        "menu_recommendations": raw_record.get("menu_recommendations", {}) or {},
    }
    if not venue["search_text"] and category == "venues":
        venue["search_text"] = (
            f"{venue['name']} located in {venue['locality']}, {venue['location']}. "
            f"Type: {venue['type']}. Capacity: {venue['capacity']} guests. "
            f"Cost: ₹{int(venue['cost_per_day'])} per day. Amenities: {amenities}."
        )
    return venue


def load_vendor_catalog(catalog_path: Optional[Path | str] = None) -> List[Dict[str, Any]]:
    """Load and normalise the JSON vendor catalog."""
    resolved_path = Path(catalog_path) if catalog_path is not None else DEFAULT_CATALOG_PATH
    if not resolved_path.exists():
        if catalog_path is None:
            return []
        raise FileNotFoundError(f"Vendor catalog not found at {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as catalog_file:
        payload = json.load(catalog_file)

    raw_vendors = payload.get("vendors", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
    vendors: List[Dict[str, Any]] = []
    for record in raw_vendors:
        normalised = _normalise_vendor_record(record)
        if normalised is not None:
            vendors.append(normalised)
    return vendors


def _location_matches(record: Dict[str, Any], target_location: str) -> bool:
    if not target_location:
        return True
    normalized_target = _normalize_text(target_location)
    if not normalized_target:
        return True
    return _record_is_in_city(record, normalized_target)


def _style_matches(record: Dict[str, Any], venue_style: Optional[str]) -> bool:
    if not venue_style:
        return True
    style = _normalize_text(venue_style)
    if not style:
        return True
    record_type = _normalize_text(record.get("type", ""))
    amenities = " ".join(_normalize_text(item) for item in record.get("amenities", []) or [])
    if style in record_type or style in amenities:
        return True
    if "outdoor" in style and any(token in record_type for token in ["garden", "outdoor", "courtyard", "lawn", "resort", "banquet"]):
        return True
    if "roof" in style and any(token in record_type for token in ["roof", "rooftop", "terrace"]):
        return True
    if "indoor" in style and any(token in record_type for token in ["indoor", "hall", "atrium", "banquet"]):
        return True
    if "garden" in style and any(token in record_type for token in ["garden", "lawn", "resort", "courtyard"]):
        return True
    if "banquet" in style and any(token in record_type for token in ["banquet", "hall", "ballroom", "convention"]):
        return True
    if "resort" in style and any(token in record_type for token in ["resort", "garden", "lawn", "courtyard"]):
        return True
    return False


def _venue_sort_key(record: Dict[str, Any], target_attendance: int, budget_limit: float) -> tuple:
    capacity = int(record.get("capacity") or 0)
    cost = float(record.get("cost_per_day") or 0.0)
    return (
        abs(capacity - target_attendance),
        abs(cost - budget_limit) if budget_limit > 0 else 0.0,
        -float(record.get("rating", 0.0)),
    )


def _occasion_key(event_type: str) -> str:
    normalized = _normalize_text(event_type)
    if any(term in normalized for term in ("birthday", "private party", "party", "celebration")):
        return "birthday"
    if any(term in normalized for term in ("hackathon", "tech fest", "technology event", "college fest")):
        return "tech_fest"
    if any(term in normalized for term in ("corporate", "leadership", "summit", "conference", "business")):
        return "corporate"
    return "general"


def _occasion_score(record: Dict[str, Any], event_type: str, category: str) -> int:
    profile = _occasion_key(event_type)
    if profile == "general":
        return 0

    suitable_for = record.get("suitable_for", [])
    if isinstance(suitable_for, str):
        suitable_for = [suitable_for]
    suitable_text = " ".join(_normalize_text(value) for value in suitable_for)
    score = 6 if any(_normalize_text(term) in suitable_text for term in OCCASION_TERMS[profile]) else 0

    searchable = " ".join(
        _normalize_text(value)
        for value in [
            record.get("name", ""),
            record.get("type", ""),
            record.get("description", ""),
            record.get("vibe", ""),
            record.get("tags", []),
            record.get("amenities", []),
            record.get("search_text", ""),
        ]
    )
    score += sum(1 for term in OCCASION_SEMANTICS[profile] if _normalize_text(term) in searchable)

    if category == "caterers":
        menu_recommendations = record.get("menu_recommendations", {})
        menu = menu_recommendations.get(profile, "") if isinstance(menu_recommendations, dict) else ""
        score += sum(1 for term in OCCASION_SEMANTICS[profile] if _normalize_text(term) in _normalize_text(menu))
    return score


def _occasion_label(event_type: str) -> str:
    profile = _occasion_key(event_type)
    return {
        "birthday": "🎉 Best for Birthdays",
        "corporate": "💼 Tailored for Corporate Summits",
        "tech_fest": "⚡ Built for Tech Fests",
    }.get(profile, "Event-type match")


def _base_vendor_result(record: Dict[str, Any], match_label: str, match_reason: str, is_dynamic_fallback: bool = False, display_note: Optional[str] = None) -> Dict[str, Any]:
    result = {
        "id": record.get("id"),
        "name": record.get("name"),
        "category": record.get("category"),
        "location": record.get("location"),
        "locality": record.get("locality"),
        "capacity": int(record.get("capacity") or 0),
        "cost_per_day": float(record.get("cost_per_day") or 0.0),
        "type": record.get("type"),
        "amenities": record.get("amenities", []),
        "contact": record.get("contact"),
        "rating": float(record.get("rating") or 0.0),
        "match_label": match_label,
        "match_reason": match_reason,
        "is_dynamic_fallback": bool(is_dynamic_fallback),
        "display_note": display_note,
        "search_text": record.get("search_text") or "",
        "website": record.get("website") or "",
        "suitable_for": record.get("suitable_for", []),
        "vibe": record.get("vibe", "Versatile / Event-ready setup"),
        "menu_recommendations": record.get("menu_recommendations", {}),
        "occasion_fit": match_label if not is_dynamic_fallback else "Versatile city fallback",
        "occasion_note": display_note,
    }
    return result


def _build_dynamic_note(user_location: str) -> str:
    clean = str(user_location or "custom location").strip() or "custom location"
    return f"Custom adapted venue specification recommended for '{clean}' based on capacity and budget requirements."


def search_venues(location: str, max_venue_budget: float, attendee_count: int, venue_style: Optional[str] = None, limit: int = 3, event_type: str = "") -> List[Dict[str, Any]]:
    """Return occasion-ranked venue recommendations within the requested city only."""
    records = [record for record in load_vendor_catalog() if record.get("category") == "venues"]
    if not records:
        return []

    target_location = str(location or "").strip()
    target_attendance = max(1, int(attendee_count or 0))
    budget_limit = max(0.0, float(max_venue_budget or 0.0))
    if budget_limit <= 0:
        budget_limit = float("inf")

    records = _filter_records_by_city(records, target_location)
    if target_location and not records:
        return []

    capacity_fit = [record for record in records if int(record.get("capacity") or 0) >= target_attendance]
    occasion_fit = [record for record in capacity_fit if _occasion_score(record, event_type, "venues") >= 6]
    use_fallback = bool(event_type and _occasion_key(event_type) != "general" and not occasion_fit)
    candidates = occasion_fit or capacity_fit
    if not candidates:
        candidates = records
        use_fallback = bool(event_type and _occasion_key(event_type) != "general")

    def ranking_key(record: Dict[str, Any]) -> tuple:
        cost = float(record.get("cost_per_day") or 0.0)
        style_penalty = 0 if _style_matches(record, venue_style) else 1
        budget_penalty = max(0.0, cost - budget_limit)
        return (
            -_occasion_score(record, event_type, "venues"),
            style_penalty,
            budget_penalty,
            abs(int(record.get("capacity") or 0) - target_attendance),
            -float(record.get("rating") or 0.0),
        )

    ranked: List[Dict[str, Any]] = []
    for record in sorted(candidates, key=ranking_key)[:limit]:
        is_fallback = use_fallback
        occasion_label = "Versatile city fallback" if is_fallback else _occasion_label(event_type)
        adaptation_note = (
            f"No dedicated {event_type} venue was found in {record.get('location')}; this versatile same-city venue can adapt its layout and setup."
            if is_fallback
            else f"Occasion fit for {event_type or 'your event'} in {record.get('location')}."
        )
        if int(record.get("capacity") or 0) < target_attendance:
            adaptation_note += f" Capacity is {record.get('capacity')} guests, below the requested {target_attendance}."
        result = _base_vendor_result(
            record,
            match_label=occasion_label,
            match_reason=f"Ranked for {event_type or 'event type'}, city, capacity, style, and budget.",
            is_dynamic_fallback=is_fallback,
            display_note=adaptation_note,
        )
        result["occasion_fit"] = occasion_label
        result["occasion_note"] = adaptation_note if is_fallback else None
        ranked.append(result)
    return ranked


def search_caterers(location: str, max_caterer_budget: float, attendee_count: int, limit: int = 3, event_type: str = "") -> List[Dict[str, Any]]:
    """Return occasion-ranked caterers within the requested city only."""
    records = [record for record in load_vendor_catalog() if record.get("category") == "caterers"]
    if not records:
        return []

    target_location = str(location or "").strip()
    target_attendance = max(1, int(attendee_count or 0))
    budget_limit = max(0.0, float(max_caterer_budget or 0.0))
    if budget_limit <= 0:
        budget_limit = float("inf")

    records = _filter_records_by_city(records, target_location)
    if target_location and not records:
        return []

    candidates: List[Dict[str, Any]] = []
    for record in records:
        if int(record.get("capacity") or 0) < target_attendance:
            continue
        if _location_matches(record, target_location):
            candidates.append(record)

    if not candidates:
        return []

    profile = _occasion_key(event_type)
    ordered = sorted(candidates, key=lambda item: (-_occasion_score(item, event_type, "caterers"), abs(float(item.get("cost_per_day") or 0.0) - budget_limit), -float(item.get("rating") or 0.0)))
    ranked = []
    for record in ordered[:limit]:
        ranked.append(
            _base_vendor_result(
                record,
                match_label=_occasion_label(event_type),
                match_reason=f"Menu recommendation tailored for {event_type or 'your event'} within the requested city.",
                display_note=f"📍 {record.get('locality', '')}, {record.get('location', '')}".strip(", ") if record.get("location") else None,
            )
        )
        menu_recommendations = record.get("menu_recommendations", {})
        ranked[-1]["menu_recommendation"] = menu_recommendations.get(profile) if isinstance(menu_recommendations, dict) else None
        ranked[-1]["occasion_fit"] = _occasion_label(event_type)
    return ranked[:limit]


def search_av_rentals(location: str, max_av_budget: float, attendee_count: int, limit: int = 3, event_type: str = "") -> List[Dict[str, Any]]:
    """Return ranked AV rental recommendations within the requested city only."""
    records = [record for record in load_vendor_catalog() if record.get("category") == "av_rentals"]
    if not records:
        return []

    target_location = str(location or "").strip()
    target_attendance = max(1, int(attendee_count or 0))
    budget_limit = max(0.0, float(max_av_budget or 0.0))
    if budget_limit <= 0:
        budget_limit = float("inf")

    records = _filter_records_by_city(records, target_location)
    if target_location and not records:
        return []

    candidates: List[Dict[str, Any]] = []
    for record in records:
        if int(record.get("capacity") or 0) < target_attendance:
            continue
        if _location_matches(record, target_location):
            candidates.append(record)

    if not candidates:
        return []

    ordered = sorted(candidates, key=lambda item: (-_occasion_score(item, event_type, "av_rentals"), abs(float(item.get("cost_per_day") or 0.0) - budget_limit), -float(item.get("rating") or 0.0)))
    ranked = []
    for record in ordered[:limit]:
        ranked.append(
            _base_vendor_result(
                record,
                match_label="Best AV fit" if float(record.get("cost_per_day") or 0.0) <= budget_limit else "AV alternate",
                match_reason="AV fit based on event scale and budget ceiling.",
                display_note=f"📍 {record.get('locality', '')}, {record.get('location', '')}".strip(", ") if record.get("location") else None,
            )
        )
    return ranked[:limit]


def search_vendors(
    query: str = "",
    category: Optional[str] = None,
    max_budget: Optional[float] = None,
    attendee_count: Optional[int] = None,
    limit: int = 5,
    db_dir: Optional[Path | str] = None,
    event_type: str = "",
) -> List[Dict[str, Any]]:
    """Backward-compatible vendor search function with dynamic, resilient location matching."""
    categories = [category] if category else ["venues", "caterers", "av_rentals"]
    result: List[Dict[str, Any]] = []

    for item in categories:
        item_name = str(item).strip().lower()
        if item_name not in VALID_CATEGORIES:
            continue

        if item_name == "venues":
            result.extend(
                search_venues(
                    location=str(query or "").strip(),
                    max_venue_budget=float(max_budget or 10**9),
                    attendee_count=int(attendee_count or 0),
                    limit=max(1, int(limit)),
                    event_type=event_type,
                )
            )
        elif item_name == "caterers":
            result.extend(
                search_caterers(
                    location=str(query or "").strip(),
                    max_caterer_budget=float(max_budget or 10**9),
                    attendee_count=int(attendee_count or 0),
                    limit=max(1, int(limit)),
                    event_type=event_type,
                )
            )
        elif item_name == "av_rentals":
            result.extend(
                search_av_rentals(
                    location=str(query or "").strip(),
                    max_av_budget=float(max_budget or 10**9),
                    attendee_count=int(attendee_count or 0),
                    limit=max(1, int(limit)),
                    event_type=event_type,
                )
            )

    if not result:
        venue_pool = search_venues(
            location=str(query or "").strip(),
            max_venue_budget=float(max_budget or 10**9),
            attendee_count=int(attendee_count or 0),
            limit=2,
            event_type=event_type,
        )
        if venue_pool:
            result.extend(venue_pool)

    return result[:max(2, int(limit))]


@tool("VendorSearchTool")
def vendor_search_tool(
    query: str = "",
    category: Optional[str] = None,
    max_budget: Optional[float] = None,
    attendee_count: Optional[int] = None,
    limit: int = 5,
    db_dir: Optional[Path | str] = None,
    event_type: str = "",
) -> str:
    """Grounded vendor retrieval across all catalog categories with resilient ranking."""
    results = search_vendors(
        query=query,
        category=category,
        max_budget=max_budget,
        attendee_count=attendee_count,
        limit=limit,
        db_dir=db_dir,
        event_type=event_type,
    )
    return json.dumps(results, ensure_ascii=False)


class VendorSearchTool(BaseTool):
    name: str = "VendorSearchTool"
    description: str = "Searches the local vendor catalog for ranked venue, caterer, and AV recommendations using flexible city, budget, and capacity matching."

    def _run(
        self,
        query: str = "",
        category: Optional[str] = None,
        max_budget: Optional[float] = None,
        attendee_count: Optional[int] = None,
        limit: int = 5,
        db_dir: Optional[Path | str] = None,
        event_type: str = "",
    ) -> str:
        results = search_vendors(
            query=query,
            category=category,
            max_budget=max_budget,
            attendee_count=attendee_count,
            limit=limit,
            db_dir=db_dir,
            event_type=event_type,
        )
        return json.dumps(results, ensure_ascii=False)


VendorSearchTool.model_rebuild()
