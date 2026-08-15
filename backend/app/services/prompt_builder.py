import json

from app.schemas.trip import AttractionCandidate, DayPlan, FoodCandidate, Spot, TripPlan, WeatherInfo


def build_trip_prompt(destination: str, days: int, budget: int, preferences: list[str]) -> str:
    preference_text = "、".join(preferences) if preferences else "无特别偏好"

    example = TripPlan(
        destination=destination,
        days=days,
        budget=budget,
        preferences=preferences,
        overview="行程总览：一句话概括这次旅行的主题和亮点。",
        daily_plans=[
            DayPlan(
                day=1,
                theme="市区人文与地道美食",
                spots=[
                    Spot(
                        name="宽窄巷子",
                        address="成都市青羊区",
                        duration="2-3小时",
                        description="成都经典街区，适合感受市井生活。",
                        location="104.053307,30.663869",
                    ),
                    Spot(
                        name="人民公园鹤鸣茶社",
                        address="成都市青羊区",
                        duration="1-2小时",
                        description="体验盖碗茶和成都慢生活。",
                    ),
                ],
            )
        ],
        total_cost=budget,
        notes=["提前预订热门餐厅", "景点门票建议提前在官方平台购买"],
    )

    return f"""请为以下旅行需求生成 JSON 格式的完整行程规划，只输出 JSON，不要输出任何其他文字。

需求：
- 目的地：{destination}
- 天数：{days}天
- 预算：{budget}元
- 偏好：{preference_text}

必须遵守：
1. 只输出 JSON，不要输出 Markdown 代码块，不要输出解释。
2. 字段名必须严格使用示例中的字段名；每天的字段叫 theme，不要使用 title。
3. daily_plans 必须包含 {days} 天，day 从 1 开始递增。
4. 每天 spots 至少 2 个。
5. total_cost 不要超过预算 {budget}。
6. daily_plans[].foods 必须是对象数组，每个对象包含 name、cuisine、price_range、address、description、best_time 字段；不要输出字符串数组。
7. 不要输出 budget_report、hotels、weather、nearby、routes 字段，这些由其他模块补充。

JSON 结构示例：
{example.model_dump_json(indent=2, ensure_ascii=False)}
"""


def build_itinerary_prompt(
    destination: str,
    days: int,
    budget: int,
    preferences: list[str],
    requirement: dict,
    attractions: list[AttractionCandidate],
    foods: list[FoodCandidate],
    pace: str = "standard",
    weather: WeatherInfo | None = None,
) -> str:
    preference_text = "、".join(preferences) if preferences else "无特别偏好"
    pace_text = {
        "compact": "紧凑节奏：每天安排 4-5 个景点，控制每个景点停留时间，行程密度高。",
        "standard": "标准节奏：每天安排 3-4 个景点，景点与美食交替，行程张弛有度。",
        "relaxed": "舒适节奏：每天安排 2-3 个景点，放慢停留时间，预留休息和自由活动。",
    }.get(pace, "标准节奏：每天安排 3-4 个景点，景点与美食交替，行程张弛有度。")

    example = TripPlan(
        destination=destination,
        days=days,
        budget=budget,
        preferences=preferences,
        overview="行程总览：一句话概括这次旅行的主题和亮点。",
        daily_plans=[
            DayPlan(
                day=1,
                theme="市区人文与地道美食",
                spots=[
                    Spot(
                        name="宽窄巷子",
                        address="成都市青羊区",
                        duration="2-3小时",
                        description="成都经典街区，适合感受市井生活。",
                    )
                ],
                foods=[
                    FoodCandidate(
                        name="龙抄手",
                        cuisine="成都小吃",
                        price_range="30-50元",
                        address="成都市春熙路",
                        description="成都名小吃",
                        best_time="早餐或午餐",
                    )
                ],
            )
        ],
        total_cost=budget,
        notes=["提前预订热门餐厅", "景点门票建议提前在官方平台购买"],
    )

    requirement_text = json.dumps(requirement, ensure_ascii=False, indent=2)
    attraction_text = json.dumps(
        [item.model_dump() for item in attractions], ensure_ascii=False, indent=2
    )
    food_text = json.dumps(
        [item.model_dump() for item in foods], ensure_ascii=False, indent=2
    )

    weather_text = ""
    if weather and weather.forecasts:
        lines = []
        for index, forecast in enumerate(weather.forecasts[: max(days, 7)], start=1):
            lines.append(
                f"Day {index}: {forecast.date} {forecast.week} "
                f"{forecast.day_weather}/{forecast.night_weather} "
                f"{forecast.temp_min}-{forecast.temp_max}℃ "
                f"降水{forecast.precipitation_probability}% {forecast.suggestion}"
            )
        weather_text = "\n\n每日天气参考：\n" + "\n".join(lines) + "\n\n要求：雨天优先安排室内景点或把雨天备选建议写入 notes。"
    return f"""请根据候选景点和候选美食生成 JSON 格式的完整行程规划，只输出 JSON，不要输出任何其他文字。

需求：
- 目的地：{destination}
- 天数：{days}天
- 预算：{budget}元
- 偏好：{preference_text}
- 节奏：{pace_text}
- 方案主题：{requirement.get('travel_style') or '综合体验'}

必须遵守：
1. 只输出 JSON，不要输出 Markdown 代码块，不要输出解释。
2. 景点只能从“候选景点”中选择，不要编造清单外的景点。
3. 美食只能从“候选美食”中选择，不要编造清单外的餐厅。
4. daily_plans 必须包含 {days} 天，day 从 1 开始递增。
5. 每天 spots 至少 2 个，foods 至少 1 个。
6. total_cost 不要超过预算 {budget}。
7. 不要输出 budget_report 字段，预算审核由后续 Agent 负责。
8. 每个 spot 必须复制候选景点中的 location 字段，不要编造坐标。
9. 每个 food 必须复制候选美食中的 location 字段，不要编造坐标。
10. daily_plans[].foods 必须是对象数组，每个对象包含 name、cuisine、price_range、address、description、best_time 字段；不要输出字符串数组。
11. 不要输出 hotels、weather、nearby、routes 字段，这些由其他模块补充。

需求分析：
{requirement_text}

候选景点：
{attraction_text}

候选美食：
{food_text}{weather_text}

JSON 结构示例：
{example.model_dump_json(indent=2, ensure_ascii=False, exclude={"budget_report"})}
"""
