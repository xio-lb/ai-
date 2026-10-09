"""Per-day route ordering.

The LLM picks good spots but has no sense of geography, so a day can zig-zag
across the city and the returned path costs stay high. This module reorders the
stops of each day with a nearest-neighbour pass followed by 2-opt refinement.

Constraints kept on purpose:

* The first stop of a day stays first - it is what the traveller sees after
  leaving the hotel.
* Spots and restaurants keep their relative slots, so meal times stay roughly
  where the LLM placed them instead of being optimised into lunch at 9am.
* A reorder is only accepted when it saves at least ``MIN_IMPROVEMENT`` of the
  open-path length, so stable plans are not shuffled for noise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.schemas.trip import DayPlan

EARTH_RADIUS_METERS = 6371000.0
MIN_IMPROVEMENT = 0.10


@dataclass
class DayOrder:
    day: int
    original: list[str] = field(default_factory=list)
    optimized: list[str] = field(default_factory=list)
    distance_before_meters: float = 0.0
    distance_after_meters: float = 0.0
    changed: bool = False


def parse_location(value: str) -> tuple[float, float] | None:
    if not value:
        return None
    try:
        lng, lat = (float(part) for part in str(value).split(","))
    except (TypeError, ValueError):
        return None
    if not (73 <= lng <= 135 and 18 <= lat <= 54):
        return None
    if (lng, lat) == (0.0, 0.0):
        return None
    return lng, lat


def haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lng1, lat1 = a
    lng2, lat2 = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(min(1.0, math.sqrt(h)))


def path_length_meters(points: list[tuple[float, float]]) -> float:
    return sum(haversine_meters(points[i], points[i + 1]) for i in range(len(points) - 1))


def nearest_neighbour_order(points: list[tuple[float, float]]) -> list[int]:
    if len(points) <= 2:
        return list(range(len(points)))

    remaining = set(range(1, len(points)))
    order = [0]
    while remaining:
        current = points[order[-1]]
        nxt = min(remaining, key=lambda index: haversine_meters(current, points[index]))
        order.append(nxt)
        remaining.discard(nxt)
    return order


def two_opt_order(points: list[tuple[float, float]], order: list[int], max_passes: int = 40) -> list[int]:
    """Classic 2-opt: reverse a sub-path whenever it shortens the total length."""
    if len(order) < 3:
        return order

    best = list(order)
    best_length = path_length_meters([points[index] for index in best])

    for _ in range(max_passes):
        improved = False
        for i in range(0, len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                # The first stop is pinned, so skip swaps that move it away.
                if candidate[0] != order[0]:
                    continue
                length = path_length_meters([points[index] for index in candidate])
                if length + 1e-6 < best_length:
                    best, best_length = candidate, length
                    improved = True
        if not improved:
            break
    return best


def _stop_keys(day: DayPlan) -> list[str]:
    keys: list[str] = []
    max_len = max(len(day.spots), len(day.foods))
    for index in range(max_len):
        if index < len(day.spots):
            keys.append(f"spot:{index}")
        if index < len(day.foods):
            keys.append(f"food:{index}")
    return keys


def _locations_for_keys(day: DayPlan, keys: list[str]) -> list[tuple[float, float] | None]:
    locations: list[tuple[float, float] | None] = []
    for key in keys:
        kind, _, raw_index = key.partition(":")
        item = day.spots[int(raw_index)] if kind == "spot" else day.foods[int(raw_index)]
        locations.append(parse_location(item.location))
    return locations


def _apply_key_order(day: DayPlan, keys: list[str]) -> None:
    spot_order = [int(key.split(":")[1]) for key in keys if key.startswith("spot:")]
    food_order = [int(key.split(":")[1]) for key in keys if key.startswith("food:")]
    day.spots = [day.spots[index] for index in spot_order]
    day.foods = [day.foods[index] for index in food_order]


def optimize_plan_days(plan) -> list[DayOrder]:
    """Return per-day ordering metadata and apply accepted reorders in place."""
    results: list[DayOrder] = []
    for day in plan.daily_plans:
        keys = _stop_keys(day)
        locations = _locations_for_keys(day, keys)
        usable = [(index, location) for index, location in enumerate(locations) if location is not None]
        result = DayOrder(day=day.day, original=list(keys), optimized=list(keys))

        if len(usable) < 3:
            results.append(result)
            continue

        usable_indices = [index for index, _ in usable]
        points = [location for _, location in usable]
        greedy = nearest_neighbour_order(points)
        refined = two_opt_order(points, greedy)

        before = path_length_meters(points)
        after = path_length_meters([points[index] for index in refined])
        result.distance_before_meters = round(before, 1)
        result.distance_after_meters = round(after, 1)

        if before <= 0 or (before - after) / before < MIN_IMPROVEMENT:
            results.append(result)
            continue

        reordered_keys = list(keys)
        for slot, usable_index in enumerate(usable_indices):
            reordered_keys[usable_index] = keys[usable_indices[refined[slot]]]

        if reordered_keys == keys:
            results.append(result)
            continue

        _apply_key_order(day, reordered_keys)
        result.optimized = list(reordered_keys)
        result.changed = True
        results.append(result)
    return results
