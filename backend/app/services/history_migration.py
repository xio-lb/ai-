"""Repair old history plans that are missing newer fields."""

from app.schemas.trip import HotelCandidate, TripPlan
from app.services.amap_client import build_route_legs


def _known_stop_names(plan: TripPlan) -> set[str]:
    names: set[str] = set()
    for day in plan.daily_plans:
        for spot in day.spots:
            if spot.name:
                names.add(spot.name)
        for food in day.foods:
            if food.name:
                names.add(food.name)
    return names


def _derive_hotel(plan: TripPlan) -> HotelCandidate | None:
    known = _known_stop_names(plan)
    for leg in plan.route_legs:
        if (
            leg.stop_type == "hotel"
            and leg.to_name
            and leg.to_name not in known
            and leg.to_location
        ):
            return HotelCandidate(
                name=leg.to_name,
                location=leg.to_location,
                category="酒店",
            )
    return None


def migrate_plan(plan: TripPlan) -> TripPlan:
    plan.hotels = plan.hotels or []
    plan.nearby = plan.nearby or []
    plan.routes = plan.routes or {}
    plan.route_legs = plan.route_legs or []
    plan.notes = plan.notes or []
    plan.preferences = plan.preferences or []
    plan.user_preferences = plan.user_preferences or []

    if not plan.transport_mode:
        plan.transport_mode = "auto"

    if not plan.hotels:
        derived = _derive_hotel(plan)
        if derived is not None:
            plan.hotels = [derived]

    if not plan.route_legs:
        hotel = plan.hotels[0] if plan.hotels else None
        try:
            plan.route_legs = build_route_legs(plan, hotel, plan.transport_mode)
        except Exception:
            plan.route_legs = []

    if plan.route_legs and not plan.routes:
        plan.routes = {leg.to_name: leg for leg in plan.route_legs if leg.to_name}

    return plan
