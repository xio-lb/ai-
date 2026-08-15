import re
from datetime import datetime

from app.schemas.trip import AttractionCandidate, FoodCandidate, HotelCandidate, TripPlan


def _normalize_name(name: str) -> str:
    return re.sub(r"[\s（）()·\-—,:：]", "", str(name or "")).lower()


def _valid_location(location: str) -> bool:
    if not location:
        return False
    try:
        lng, lat = (float(item) for item in str(location).split(","))
    except Exception:
        return False
    return 73 <= lng <= 135 and 18 <= lat <= 54 and (lng, lat) != (0.0, 0.0)


def _find_candidate(name: str, candidates: list[AttractionCandidate] | list[FoodCandidate]) -> object | None:
    key = _normalize_name(name)
    if not key:
        return None
    for candidate in candidates:
        candidate_key = _normalize_name(candidate.name)
        if key == candidate_key or key in candidate_key or candidate_key in key:
            return candidate
    return None


def _repair_locations(
    plan: TripPlan,
    attractions: list[AttractionCandidate],
    foods: list[FoodCandidate],
) -> list[str]:
    repairs: list[str] = []
    attraction_map = {_normalize_name(item.name): item for item in attractions}
    food_map = {_normalize_name(item.name): item for item in foods}

    for day in plan.daily_plans:
        for spot in day.spots:
            candidate = attraction_map.get(_normalize_name(spot.name))
            if candidate is None:
                candidate = _find_candidate(spot.name, attractions)
            if candidate is None:
                continue
            if not spot.location and candidate.location:
                spot.location = candidate.location
                repairs.append(f"修复景点坐标：{spot.name}")
            if not spot.booking_url and candidate.booking_url:
                spot.booking_url = candidate.booking_url
                spot.booking_label = candidate.booking_label

        for food in day.foods:
            candidate = food_map.get(_normalize_name(food.name))
            if candidate is None:
                candidate = _find_candidate(food.name, foods)
            if candidate is None:
                continue
            if not food.location and candidate.location:
                food.location = candidate.location
                repairs.append(f"修复餐厅坐标：{food.name}")

    return repairs


def check_quality(
    plan: TripPlan,
    attractions: list[AttractionCandidate],
    foods: list[FoodCandidate],
    hotels: list[HotelCandidate] | None = None,
) -> dict:
    issues: list[str] = []
    repairs = _repair_locations(plan, attractions, foods)

    for day in plan.daily_plans:
        for spot in day.spots:
            candidate = _find_candidate(spot.name, attractions)
            if not spot.name:
                issues.append(f"第{day.day}天存在空景点名称")
            elif candidate is None:
                issues.append(f"景点不在候选清单：{spot.name}")
            elif not _valid_location(spot.location):
                issues.append(f"景点坐标不可用：{spot.name}")

        for food in day.foods:
            candidate = _find_candidate(food.name, foods)
            if not food.name:
                issues.append(f"第{day.day}天存在空餐厅名称")
            elif candidate is None:
                issues.append(f"餐厅不在候选清单：{food.name}")
            elif not _valid_location(food.location):
                issues.append(f"餐厅坐标不可用：{food.name}")

    for hotel in hotels or plan.hotels or []:
        if hotel and hotel.name and not _valid_location(hotel.location):
            issues.append(f"酒店坐标不可用：{hotel.name}")

    if len(plan.daily_plans) != plan.days:
        issues.append(f"天数不匹配：行程有{len(plan.daily_plans)}天，要求{plan.days}天")

    for day in plan.daily_plans:
        if len(day.spots) < 2:
            issues.append(f"第{day.day}天景点不足 2 个")
        if not day.foods:
            issues.append(f"第{day.day}天缺少餐厅安排")

    return {
        "passed": not issues,
        "issues": issues,
        "repairs": repairs,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def check_route_closure(plan: TripPlan, hotel: HotelCandidate | None) -> list[str]:
    if not plan.route_legs:
        return ["路线未生成，无法确认闭环"]

    issues: list[str] = []
    for day in plan.daily_plans:
        day_legs = [leg for leg in plan.route_legs if leg.day == day.day]
        if not day_legs:
            issues.append(f"第{day.day}天没有路线")
            continue

        if hotel and day_legs[0].from_name != hotel.name:
            issues.append(f"第{day.day}天路线没有从酒店出发")

        last_leg = day_legs[-1]
        if hotel and last_leg.stop_type != "hotel" and last_leg.to_name != hotel.name:
            issues.append(f"第{day.day}天路线没有返回酒店")

        if any(not leg.polyline for leg in day_legs):
            issues.append(f"第{day.day}天部分路线缺少轨迹")

    return issues