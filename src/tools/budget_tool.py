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


def calculate_budget_breakdown(total_budget: float, attendee_count: int) -> Dict[str, Any]:
    """Return fixed allocations, per-head catering allowance, and food-risk check."""
    if not isinstance(total_budget, (int, float)):
        raise TypeError("total_budget must be numeric.")
    if not isinstance(attendee_count, int):
        raise TypeError("attendee_count must be an integer.")
    if total_budget <= 0:
        raise ValueError("total_budget must be greater than zero.")
    if attendee_count <= 0:
        raise ValueError("attendee_count must be greater than zero.")

    venue_allocation = round(total_budget * 0.30, 2)
    catering_allocation = round(total_budget * 0.40, 2)
    av_allocation = round(total_budget * 0.15, 2)
    contingency_allocation = round(total_budget * 0.15, 2)
    per_head_catering_allowance = round(catering_allocation / attendee_count, 2)
    under_minimum_food_allowance = per_head_catering_allowance < 150

    return {
        "total_budget": round(float(total_budget), 2),
        "attendee_count": attendee_count,
        "breakdown": {
            "venue": venue_allocation,
            "catering": catering_allocation,
            "av_equipment": av_allocation,
            "contingency_buffer": contingency_allocation,
        },
        "total_allocated": round(
            venue_allocation + catering_allocation + av_allocation + contingency_allocation,
            2,
        ),
        "per_head_catering_allowance": per_head_catering_allowance,
        "food_budget_warning": under_minimum_food_allowance,
        "food_budget_warning_message": (
            "Per-head catering allowance is below ₹150; this is likely insufficient to feed guests comfortably."
            if under_minimum_food_allowance
            else "Per-head catering allowance is viable for the guest count."
        ),
        "allocation_percentages": {
            "venue": 30,
            "catering": 40,
            "av_equipment": 15,
            "contingency_buffer": 15,
        },
    }


@tool("BudgetCalculatorTool")
def budget_calculator_tool(total_budget: float, attendee_count: int) -> str:
    """Calculate deterministic budget allocations and highlight unviable food allowance."""
    return json.dumps(calculate_budget_breakdown(total_budget, attendee_count), ensure_ascii=False)


class BudgetCalculatorTool(BaseTool):
    name: str = "BudgetCalculatorTool"
    description: str = (
        "Deterministic event budget allocator with fixed 30/40/15/15 split and a per-head catering risk flag."
    )

    def _run(self, total_budget: float, attendee_count: int) -> str:
        result = calculate_budget_breakdown(total_budget, attendee_count)
        return json.dumps(result, ensure_ascii=False)


BudgetCalculatorTool.model_rebuild()
