from app.schemas.trip import AttractionCandidate, FoodCandidate, TripPlan, WeatherInfo
from app.services.deepseek_client import chat_json
from app.services.prompt_builder import build_itinerary_prompt
from app.services.amap_client import build_booking_label, build_booking_url

SYSTEM_PROMPT = "你是资深行程编排专家，只从候选清单中选择景点和美食，只输出 JSON。"


def _fill_locations(
    plan: TripPlan,
    attractions: list[AttractionCandidate],
    foods: list[FoodCandidate],
) -> TripPlan:
    attraction_map = {item.name: item.location for item in attractions}
    attraction_booking_map = {item.name: (item.booking_url, item.booking_label) for item in attractions}
    food_map = {item.name: item.location for item in foods}

    for day in plan.daily_plans:
        for spot in day.spots:
            if not spot.location and spot.name in attraction_map:
                spot.location = attraction_map[spot.name]
            if spot.name in attraction_booking_map:
                booking_url, booking_label = attraction_booking_map[spot.name]
                if not spot.booking_url and booking_url:
                    spot.booking_url = booking_url
                if not spot.booking_label and booking_label:
                    spot.booking_label = booking_label
            if not spot.booking_url:
                spot.booking_url = build_booking_url(spot.name)
                spot.booking_label = build_booking_label(spot.name)

        for food in day.foods:
            if not food.location and food.name in food_map:
                food.location = food_map[food.name]

    return plan


def generate_trip_plan(
    requirement: dict,
    attractions: list[AttractionCandidate],
    foods: list[FoodCandidate],
    feedback: str | None = None,
    instruction: str | None = None,
    current_plan: TripPlan | None = None,
    pace: str = "standard",
    weather: WeatherInfo | None = None,
) -> TripPlan:
    prompt = build_itinerary_prompt(
        destination=requirement["destination"],
        days=int(requirement["days"]),
        budget=int(requirement["budget"]),
        preferences=requirement.get("preferences", []),
        requirement=requirement,
        attractions=attractions,
        foods=foods,
        pace=pace,
        weather=weather,
    )

    if instruction:
        prompt += f"""

用户调整要求：{instruction}
请根据调整要求生成行程，尽量保留当前行程中不需要改动的部分。
"""

    if current_plan:
        prompt += f"""

当前行程（请保留不需要修改的部分）：
{current_plan.model_dump_json(indent=2, ensure_ascii=False, exclude={"budget_report"})}
"""

    if feedback:
        prompt += f"""

预算校验反馈（必须遵守）：
{feedback}
"""

    data = chat_json(
        prompt,
        system_prompt=SYSTEM_PROMPT,
        prompt_name="itinerary_generate",
    )
    data.pop("budget_report", None)

    plan = TripPlan.model_validate(data)
    return _fill_locations(plan, attractions, foods)
