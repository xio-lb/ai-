import json

from app.schemas.trip import (
    AttractionCandidate,
    DayPlan,
    FoodCandidate,
    TripPlan,
    WeatherInfo,
)
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


def repair_trip_days(
    plan: TripPlan,
    invalid_days: list[int],
    attractions: list[AttractionCandidate],
    foods: list[FoodCandidate],
    issues: list[str] | None = None,
    weather: WeatherInfo | None = None,
    weather_policy: dict | None = None,
) -> tuple[TripPlan, list[int]]:
    """Regenerate only the flagged days and merge them back into the plan."""

    targets = sorted({int(day) for day in invalid_days if 1 <= int(day) <= plan.days})
    day_map = {day.day: day for day in plan.daily_plans}
    targets = [day for day in targets if day in day_map]
    if not targets:
        return plan, []

    target_payload = [day_map[day].model_dump() for day in targets]
    issue_text = "\n".join(f"- {issue}" for issue in (issues or [])[:20]) or "- 未提供具体问题"
    attraction_text = json.dumps(
        [item.model_dump() for item in attractions], ensure_ascii=False, indent=2
    )
    food_text = json.dumps(
        [item.model_dump() for item in foods], ensure_ascii=False, indent=2
    )
    prompt = f"""只修复下列问题天数，其他天数不要输出，也不要改动。

目的地：{plan.destination}
总天数：{plan.days}

需要修复的天数与当前内容：
{json.dumps(target_payload, ensure_ascii=False, indent=2)}

质量校验发现的问题：
{issue_text}

候选景点（只能从中选择）：
{attraction_text}

候选美食（只能从中选择）：
{food_text}

必须遵守：
1. 只输出 JSON 对象，格式为 {{"daily_plans": [修复后的天数]}}，不要输出解释。
2. 只包含这些天数：{", ".join(str(day) for day in targets)}，day 字段保持不变。
3. 每天至少 2 个景点、1 个餐厅，景点和餐厅必须来自候选清单。
4. 每个 spot / food 必须复制候选清单中的 location，不要编造坐标。
5. 修复时要保留原行程中合理的部分，只调整出错的地方。
"""
    if weather_policy:
        prompt += f"""
天气策略：{weather_policy.get('summary', '')}
风险日：{weather_policy.get('risk_days', [])}
雨天优先室内景点，并在 notes 中保留备选建议。
"""
    if weather and weather.forecasts:
        forecast_text = "；".join(
            f"第{index}天 {forecast.day_weather} 降水{forecast.precipitation_probability}%"
            for index, forecast in enumerate(weather.forecasts[: plan.days], start=1)
        )
        prompt += f"\n参考预报：{forecast_text}\n"

    data = chat_json(
        prompt,
        system_prompt=SYSTEM_PROMPT,
        prompt_name="itinerary_repair_days",
    )
    repaired_days = [
        DayPlan.model_validate(item) for item in (data.get("daily_plans") or [])
    ]
    if not repaired_days:
        return plan, []

    merged = TripPlan.model_validate(
        plan.model_dump(exclude={"budget_report", "quality_report"})
    )
    replacements = {day.day: day for day in repaired_days if day.day in targets}
    if not replacements:
        return plan, []
    merged.daily_plans = [replacements.get(day.day, day) for day in merged.daily_plans]
    merged.budget_report = plan.budget_report
    merged = _fill_locations(merged, attractions, foods)
    return merged, sorted(replacements)


def generate_trip_plan(
    requirement: dict,
    attractions: list[AttractionCandidate],
    foods: list[FoodCandidate],
    feedback: str | None = None,
    instruction: str | None = None,
    current_plan: TripPlan | None = None,
    pace: str = "standard",
    weather: WeatherInfo | None = None,
    weather_policy: dict | None = None,
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
        weather_policy=weather_policy,
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
