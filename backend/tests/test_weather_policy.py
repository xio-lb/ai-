from app.agents.graph import _extract_invalid_days, build_weather_policy
from app.schemas.trip import DayPlan, Spot, TripPlan, WeatherForecast, WeatherInfo


def _plan(days: int) -> TripPlan:
    return TripPlan(
        destination="成都",
        days=days,
        budget=1000,
        daily_plans=[
            DayPlan(day=index, theme="市区", spots=[Spot(name="测试")])
            for index in range(1, days + 1)
        ],
    )


def test_weather_policy_marks_rainy_days():
    weather = WeatherInfo(
        city="成都",
        forecasts=[
            WeatherForecast(date="2026-10-10", day_weather="晴", precipitation_probability=10),
            WeatherForecast(date="2026-10-11", day_weather="中雨", precipitation_probability=80),
        ],
    )
    policy = build_weather_policy(weather)
    assert policy["risk_level"] == "medium"
    assert policy["risk_days"] == [2]
    assert "室内" in policy["day_guidance"][1]["planning"]


def test_weather_policy_handles_missing_forecast():
    policy = build_weather_policy(None)
    assert policy["risk_level"] == "unknown"
    assert policy["risk_days"] == []


def test_extract_invalid_days_requires_explicit_day_marker():
    plan = _plan(2)
    assert _extract_invalid_days(["第2天景点不足 2 个"], plan) == [2]
    assert _extract_invalid_days(["路线未生成，无法确认闭环"], plan) == []
    assert _extract_invalid_days(["天数不匹配：行程有1天，要求2天", "第1天景点不足 2 个"], plan) == []