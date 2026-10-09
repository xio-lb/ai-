import re

from app.agents.attraction_agent import recommend_attractions
from app.agents.budget_agent import validate_budget
from app.agents.food_agent import recommend_foods
from app.agents.hotel_agent import recommend_hotels
from app.schemas.trip import DayPlan, FoodCandidate, Spot, TripPlan, TripRequest
from app.services.amap_client import build_route_legs
from app.services.deepseek_client import chat_json

INTENT_SYSTEM_PROMPT = "你是旅行行程调整意图识别专家，只输出 JSON。"

ALLOWED_INTENTS = {
    "change_food",
    "lower_budget",
    "add_day",
    "remove_day",
    "change_pace",
    "change_hotel",
    "change_transport",
    "general",
}

VALID_PACES = {"compact", "standard", "relaxed"}
VALID_MODES = {"auto", "walking", "driving", "transit", "bicycling"}


def classify_adjust_intent(user_message: str, current_plan: TripPlan) -> dict:
    prompt = f"""识别下面这条行程调整请求，并输出 JSON。

当前行程：
- 目的地：{current_plan.destination}
- 天数：{current_plan.days}天
- 预算：{current_plan.budget}元
- 节奏：{current_plan.variant_pace or current_plan.variant_label or 'standard'}
- 交通：{current_plan.transport_mode or 'auto'}

用户请求：{user_message}

可选 intent：
- change_food：换餐厅、换美食、换一家吃、想吃某类菜
- lower_budget：降预算、省钱、预算不够、降到 X 元、减少花费
- add_day：加一天、多玩一天、延长行程、在第 X 天后加一天
- remove_day：少一天、缩短行程、去掉第 X 天
- change_pace：节奏调整、慢一点、快一点、轻松点、紧凑点
- change_hotel：换酒店、换住宿、住便宜点、换一家酒店
- change_transport：换交通、坐公交、步行、打车、骑行、开车
- general：其他综合性调整或无法归入以上类型

输出 JSON：
{{
  "intent": "change_food",
  "target_day": null,
  "target_name": null,
  "keyword": null,
  "budget_delta": null,
  "new_budget": null,
  "new_pace": null,
  "transport_mode": null,
  "summary": "一句话说明用户想怎么改"
}}

要求：
1. target_day 只在用户明确提到第几天时填写数字，否则为 null。
2. target_name 只在用户提到具体餐厅、景点、酒店名称时填写。
3. keyword 是用于搜索的简短关键词，例如“素食川菜”“平价小吃”。
4. new_pace 只能是 compact / standard / relaxed。
5. transport_mode 只能是 auto / walking / driving / transit / bicycling。
"""
    data = chat_json(
        prompt,
        system_prompt=INTENT_SYSTEM_PROMPT,
        prompt_name="adjust_intent",
    )
    intent = str(data.get("intent") or "general")
    if intent not in ALLOWED_INTENTS:
        intent = "general"
    if data.get("new_pace") not in VALID_PACES:
        data["new_pace"] = None
    if data.get("transport_mode") not in VALID_MODES:
        data["transport_mode"] = None
    data["intent"] = intent
    return data


def _build_request(plan: TripPlan) -> TripRequest:
    return TripRequest(
        destination=plan.destination,
        days=plan.days,
        budget=plan.budget,
        preferences=plan.preferences,
        travel_date=plan.weather.travel_date if plan.weather else "",
        pace=plan.variant_pace if plan.variant_pace in VALID_PACES else "standard",
        transport_mode=plan.transport_mode or "auto",
    )


def _requirement(plan: TripPlan, attraction_keyword: str = "", food_keyword: str = "") -> dict:
    return {
        "destination": plan.destination,
        "days": plan.days,
        "budget": plan.budget,
        "preferences": plan.preferences,
        "attraction_keywords": [
            attraction_keyword
            or (plan.preferences[0] + "景点" if plan.preferences else plan.destination + "景点")
        ],
        "food_keywords": [food_keyword or "特色美食"],
    }


def _parse_price_min(text: str) -> int:
    values = [int(value) for value in re.findall(r"\d+", text or "")]
    return values[0] if values else 99999


def _rebuild_routes(plan: TripPlan) -> None:
    hotel = plan.hotels[0] if plan.hotels else None
    try:
        legs = build_route_legs(plan, hotel, plan.transport_mode or "auto")
    except Exception:
        legs = []
    plan.route_legs = legs
    plan.routes = {leg.to_name: leg for leg in legs if leg.to_name}


def _adjust_food(plan: TripPlan, intent: dict) -> TripPlan:
    req = _build_request(plan)
    keyword = intent.get("keyword") or intent.get("target_name") or "特色美食"
    requirement = _requirement(plan, food_keyword=keyword)
    candidates = recommend_foods(req, requirement, count=6)
    if not candidates:
        candidates = recommend_foods(
            req,
            _requirement(plan, food_keyword=plan.destination + "美食"),
            count=6,
        )

    summary = intent.get("summary") or ""
    if any(word in summary for word in ("便宜", "实惠", "省钱", "低价", "降预算")):
        candidates.sort(key=lambda item: _parse_price_min(item.price_range))

    days = plan.daily_plans
    if intent.get("target_day"):
        days = [day for day in days if day.day == intent["target_day"]]
    if not days:
        days = plan.daily_plans

    for day in days:
        target_name = intent.get("target_name")
        if target_name:
            day.foods = [food for food in day.foods if food.name != target_name]
        exclude = {food.name for food in day.foods}
        picks = [food for food in candidates if food.name not in exclude][:2]
        day.foods.extend(picks)
        if not day.foods:
            day.foods = [
                FoodCandidate(
                    name="本地特色餐厅",
                    cuisine="地方菜",
                    price_range="30-80元",
                    description="根据你的调整要求推荐",
                    best_time="午晚餐",
                )
            ]

    plan.notes.append(f"已按你的要求调整餐饮：{summary or keyword}")
    return plan


def _lower_budget(plan: TripPlan, intent: dict) -> TripPlan:
    new_budget = intent.get("new_budget")
    if new_budget is None:
        new_budget = plan.budget + (intent.get("budget_delta") or 0)
    new_budget = max(100, int(new_budget))
    ratio = new_budget / max(plan.budget, 1)
    plan.budget = new_budget
    plan.total_cost = max(100, round(plan.total_cost * ratio))

    summary = intent.get("summary") or ""
    if any(word in summary for word in ("便宜", "实惠", "省钱", "平价")):
        req = _build_request(plan)
        requirement = _requirement(plan, food_keyword="平价餐厅")
        candidates = recommend_foods(req, requirement, count=6)
        candidates.sort(key=lambda item: _parse_price_min(item.price_range))
        if candidates:
            for day in plan.daily_plans:
                if day.foods:
                    day.foods = [
                        candidates[index % len(candidates)]
                        for index in range(min(len(day.foods), 2))
                    ]

    plan.notes.append(f"已把预算调整为 {plan.budget} 元：{summary or '降低整体花费'}")
    return plan


def _add_day(plan: TripPlan, intent: dict) -> TripPlan:
    old_days = max(1, len(plan.daily_plans) or plan.days)
    target_day = intent.get("target_day")
    req = _build_request(plan)
    keyword = intent.get("keyword") or ""
    requirement = _requirement(
        plan,
        attraction_keyword=keyword,
        food_keyword=keyword or "特色美食",
    )
    spots = recommend_attractions(req, requirement, count=4)
    foods = recommend_foods(req, requirement, count=4)

    if target_day and 1 <= int(target_day) <= plan.days:
        new_number = int(target_day) + 1
    else:
        new_number = plan.days + 1

    day = DayPlan(
        day=new_number,
        theme=f"新增第 {new_number} 天",
        spots=[
            Spot(
                name=spot.name,
                address=spot.address,
                duration=spot.duration,
                description=spot.description,
                location=spot.location,
                booking_url=spot.booking_url,
                booking_label=spot.booking_label,
            )
            for spot in spots[:3]
        ],
        foods=foods[:2],
    )

    if target_day and 1 <= int(target_day) <= plan.days:
        plan.daily_plans.insert(int(target_day), day)
    else:
        plan.daily_plans.append(day)

    for index, existing in enumerate(plan.daily_plans, start=1):
        existing.day = index

    plan.days = len(plan.daily_plans)
    per_day = plan.total_cost / max(1, old_days)
    plan.total_cost = round(per_day * plan.days)
    plan.notes.append(f"已新增第 {plan.days} 天：{intent.get('summary') or '按偏好补充新行程'}")
    return plan


def _remove_day(plan: TripPlan, intent: dict) -> TripPlan:
    target = intent.get("target_day") or plan.days
    old_days = max(1, len(plan.daily_plans))
    plan.daily_plans = [day for day in plan.daily_plans if day.day != target]
    if not plan.daily_plans:
        plan.notes.append("行程天数不能少于 1 天，已保留原行程")
        return plan

    for index, day in enumerate(plan.daily_plans, start=1):
        day.day = index

    plan.days = len(plan.daily_plans)
    plan.total_cost = round(plan.total_cost * plan.days / old_days)
    plan.notes.append(f"已去掉第 {target} 天：{intent.get('summary') or '缩短行程'}")
    return plan


def _change_pace(plan: TripPlan, intent: dict) -> TripPlan:
    new_pace = intent.get("new_pace") or plan.variant_pace or "standard"
    labels = {"compact": "紧凑", "standard": "标准", "relaxed": "舒适"}
    plan.variant_pace = new_pace
    plan.variant_label = labels.get(new_pace, new_pace)
    summary = intent.get("summary") or ""
    message = f"已调整节奏为{plan.variant_label}：{summary}" if summary else f"已调整节奏为{plan.variant_label}"
    plan.notes.append(message)
    return plan


def _change_hotel(plan: TripPlan, intent: dict) -> TripPlan:
    req = _build_request(plan)
    hotels = recommend_hotels(req, count=5)
    if hotels:
        plan.hotels = hotels
    plan.notes.append(f"已更新酒店推荐：{intent.get('summary') or '按你的要求重新筛选'}")
    return plan


def _change_transport(plan: TripPlan, intent: dict) -> TripPlan:
    mode = intent.get("transport_mode") or plan.transport_mode or "auto"
    plan.transport_mode = mode
    summary = intent.get("summary") or ""
    message = f"已切换交通方式：{summary}" if summary else f"已切换交通方式为{mode}"
    plan.notes.append(message)
    return plan


HANDLERS = {
    "change_food": _adjust_food,
    "lower_budget": _lower_budget,
    "add_day": _add_day,
    "remove_day": _remove_day,
    "change_pace": _change_pace,
    "change_hotel": _change_hotel,
    "change_transport": _change_transport,
}


def apply_precise_adjust(current_plan: TripPlan, user_message: str) -> TripPlan | None:
    try:
        intent = classify_adjust_intent(user_message, current_plan)
    except Exception:
        return None

    handler = HANDLERS.get(intent.get("intent"))
    if handler is None:
        return None

    plan = current_plan.model_copy(deep=True)
    try:
        plan = handler(plan, intent)
    except Exception:
        return None

    try:
        _rebuild_routes(plan)
    except Exception:
        pass

    try:
        report = validate_budget(plan)
    except Exception:
        report = None
    plan.budget_report = report
    return plan
