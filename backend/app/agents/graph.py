import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.attraction_agent import recommend_attractions
from app.agents.budget_agent import validate_budget
from app.agents.food_agent import recommend_foods
from app.agents.hotel_agent import recommend_hotels
from app.agents.itinerary_agent import generate_trip_plan, repair_trip_days
from app.agents.quality_agent import check_quality, check_route_closure
from app.agents.requirement_agent import analyze_requirement
from app.agents.weather_agent import fetch_weather
from app.schemas.trip import (
    AttractionCandidate,
    FoodCandidate,
    HotelCandidate,
    NearbyPoi,
    RouteInfo,
    TripPlan,
    TripRequest,
    WeatherInfo,
)
from app.services.amap_client import build_route_legs, search_nearby_pois
from app.services import context_cache
from app.services.graph_checkpoint import SyncMemorySaver
from app.services.route_optimizer import optimize_plan_days
from app.services.observability import (
    instrument_node,
    record_budget,
    record_context_reuse,
    record_quality,
    record_retry,
    record_route,
    record_route_optimization,
)
from app.services.cancellation import raise_if_cancelled
from app.services.progress import report_progress


class AgentState(TypedDict):
    request: TripRequest
    requirement: dict
    attractions: list[AttractionCandidate]
    foods: list[FoodCandidate]
    hotels: list[HotelCandidate]
    weather: WeatherInfo | None
    plan: TripPlan | None
    feedback: str | None
    retry_count: int
    instruction: str | None
    current_plan: TripPlan | None
    nearby: list[NearbyPoi]
    routes: dict[str, RouteInfo]
    invalid_days: list[int]
    weather_policy: dict


def _requirement_keywords(requirement: dict, key: str) -> list[str]:
    return [str(item) for item in (requirement.get(key) or []) if str(item).strip()]


def _travel_scope(request: TripRequest) -> str:
    return (request.travel_date or "")[:7]


def _cached_context(kind: str, state: AgentState, loader, keywords: list[str] | None = None):
    request = state["request"]
    value, hit = context_cache.get_or_load(
        kind=kind,
        destination=request.destination,
        loader=loader,
        scope=_travel_scope(request),
        keywords=keywords,
    )
    record_context_reuse(kind, hit)
    return value


def build_weather_policy(weather: WeatherInfo | None) -> dict:
    """Turn the forecast into an explicit per-day outdoor/indoor strategy."""

    if weather is None or not weather.forecasts:
        return {
            "risk_level": "unknown",
            "summary": "没有可用预报，按常规安排并在 notes 中保留弹性。",
            "risk_days": [],
            "day_guidance": [],
            "notes": ["出发前再次查看天气，必要时调整户外行程。"],
        }

    risky_words = ("雨", "雪", "雷", "冰", "霾", "风")
    day_guidance = []
    risk_days = []
    for index, forecast in enumerate(weather.forecasts, start=1):
        combined = f"{forecast.day_weather}{forecast.night_weather}"
        precipitation = int(forecast.precipitation_probability or 0)
        is_risky = precipitation >= 50 or any(word in combined for word in risky_words)
        if is_risky:
            planning = "优先室内景点（博物馆、展馆、商场、美食体验），户外景点配可替换的备选。"
            risk_days.append(index)
        else:
            planning = "可安排户外景点，注意防晒和补水。"
        day_guidance.append(
            {
                "day": index,
                "date": forecast.date,
                "weather": combined or forecast.day_weather,
                "precipitation_probability": precipitation,
                "planning": planning,
            }
        )

    if len(risk_days) >= 2:
        risk_level = "high"
        summary = f"有 {len(risk_days)} 天存在降水或恶劣天气风险，需要室内外混排。"
    elif risk_days:
        risk_level = "medium"
        summary = f"第 {', '.join(str(day) for day in risk_days)} 天存在天气风险，需要安排室内替代。"
    else:
        risk_level = "low"
        summary = "天气整体适合出行，按户外为主安排。"

    notes = []
    if risk_days:
        notes.append("雨天当天不要安排需要长时间步行的户外景点，室内景点的顺序可以前后调整。")
        notes.append("为风险日准备一个同区域的室内备选景点和一家附近餐厅。")
    return {
        "risk_level": risk_level,
        "summary": summary,
        "risk_days": risk_days,
        "day_guidance": day_guidance,
        "notes": notes,
    }


def _extract_invalid_days(issues: list[str], plan: TripPlan) -> list[int]:
    if any("天数不匹配" in str(issue) for issue in issues):
        return []
    days: set[int] = set()
    for issue in issues:
        match = re.search(r"第\s*(\d+)\s*天", str(issue))
        if match:
            days.add(int(match.group(1)))
    return sorted(day for day in days if 1 <= day <= plan.days)


def analyze_node(state: AgentState) -> dict:
    raise_if_cancelled()
    report_progress("正在解析行程需求")

    return {
        "requirement": analyze_requirement(
            state["request"],
            instruction=state.get("instruction"),
        )
    }


def attraction_node(state: AgentState) -> dict:
    raise_if_cancelled()
    report_progress("正在筛选景点")

    keywords = _requirement_keywords(state["requirement"], "attraction_keywords")
    attractions = _cached_context(
        "attractions",
        state,
        lambda: recommend_attractions(state["request"], state["requirement"], count=8),
        keywords=keywords,
    )
    return {"attractions": attractions}


def food_node(state: AgentState) -> dict:
    raise_if_cancelled()
    report_progress("正在筛选美食")

    keywords = _requirement_keywords(state["requirement"], "food_keywords")
    foods = _cached_context(
        "foods",
        state,
        lambda: recommend_foods(state["request"], state["requirement"], count=8),
        keywords=keywords,
    )
    return {"foods": foods}


def hotel_node(state: AgentState) -> dict:
    raise_if_cancelled()
    report_progress("正在筛选酒店")

    hotels = _cached_context(
        "hotels",
        state,
        lambda: recommend_hotels(state["request"], count=6),
        keywords=[],
    )
    return {"hotels": hotels}


def weather_node(state: AgentState) -> dict:
    raise_if_cancelled()
    report_progress("正在获取天气")

    request = state["request"]
    weather = _cached_context(
        "weather",
        state,
        lambda: fetch_weather(request.destination, request.travel_date),
        keywords=[request.travel_date],
    )
    return {
        "weather": weather,
        "weather_policy": build_weather_policy(weather),
    }


def itinerary_node(state: AgentState) -> dict:
    raise_if_cancelled()
    report_progress("正在编排每日行程")

    plan = generate_trip_plan(
        requirement=state["requirement"],
        attractions=state["attractions"],
        foods=state["foods"],
        feedback=state.get("feedback"),
        instruction=state.get("instruction"),
        current_plan=state.get("current_plan"),
        pace=state["request"].pace,
        weather=state.get("weather"),
        weather_policy=state.get("weather_policy"),
    )
    return {"plan": plan}


def budget_node(state: AgentState) -> dict:
    raise_if_cancelled()
    report_progress("正在核算预算")

    plan = state["plan"]
    report = validate_budget(plan)
    plan.budget_report = report
    record_budget(report)
    retry_count = state.get("retry_count", 0)

    if not report.within_budget and retry_count < 3:
        reason = f"total_cost {plan.total_cost} exceeds budget {plan.budget}"
        record_retry("budget", retry_count + 1, reason)
        return {
            "plan": plan,
            "feedback": f"当前 total_cost {plan.total_cost} 超过预算 {plan.budget}，请重新编排，确保 total_cost 不超过预算。",
            "retry_count": retry_count + 1,
        }

    return {
        "plan": plan,
        "feedback": None,
        "retry_count": retry_count,
    }


def quality_node(state: AgentState) -> dict:
    raise_if_cancelled()
    report_progress("正在校验行程质量")

    plan = state["plan"]
    report = check_quality(
        plan,
        state.get("attractions", []),
        state.get("foods", []),
        state.get("hotels", []),
    )
    plan.quality_report = report
    record_quality(report)
    retry_count = state.get("retry_count", 0)
    invalid_days = _extract_invalid_days(report["issues"], plan)

    if not report["passed"] and retry_count < 3:
        record_retry("quality", retry_count + 1, "；".join(report["issues"][:5]))
        return {
            "plan": plan,
            "feedback": "质量校验未通过：" + "；".join(report["issues"][:5]),
            "retry_count": retry_count + 1,
            "invalid_days": invalid_days,
        }

    return {
        "plan": plan,
        "feedback": None,
        "retry_count": retry_count,
        "invalid_days": [],
    }


def repair_days_node(state: AgentState) -> dict:
    """Regenerate only the days flagged by quality checks, not the whole plan."""

    raise_if_cancelled()
    report_progress("正在修复问题天数")

    plan = state["plan"]
    invalid_days = state.get("invalid_days") or []
    if not invalid_days:
        return {"plan": plan, "feedback": None}

    repaired_plan, repaired_days = repair_trip_days(
        plan=plan,
        invalid_days=invalid_days,
        attractions=state.get("attractions", []),
        foods=state.get("foods", []),
        weather=state.get("weather"),
        weather_policy=state.get("weather_policy"),
        issues=list((plan.quality_report or {}).get("issues", [])),
    )
    return {
        "plan": repaired_plan,
        "feedback": f"已局部修复第 {', '.join(str(day) for day in repaired_days)} 天",
    }


def surrounding_node(state: AgentState) -> dict:
    raise_if_cancelled()
    report_progress("正在补充周边与路线")

    plan = state["plan"]
    hotels = state.get("hotels", [])
    hotel = hotels[0] if hotels else None
    nearby: list[NearbyPoi] = []
    routes: dict[str, RouteInfo] = {}
    legs: list[RouteInfo] = []

    optimization = optimize_plan_days(plan)
    optimization_meta = []
    for item in optimization:
        record_route_optimization(
            item.day,
            item.distance_before_meters,
            item.distance_after_meters,
            item.changed,
        )
        optimization_meta.append(
            {
                "day": item.day,
                "distance_before_meters": item.distance_before_meters,
                "distance_after_meters": item.distance_after_meters,
                "changed": item.changed,
            }
        )

    if hotel:
        try:
            nearby = search_nearby_pois(
                hotel.location,
                types="110100",
                radius=3000,
                limit=5,
            )
        except Exception:
            nearby = []

        try:
            legs = build_route_legs(plan, hotel, state["request"].transport_mode)
        except Exception:
            legs = []

    routes = {leg.to_name: leg for leg in legs if leg.to_name}

    plan.hotels = hotels
    plan.weather = state.get("weather")
    plan.nearby = nearby
    plan.routes = routes
    plan.route_legs = legs
    plan.route_optimization = optimization_meta
    plan.transport_mode = state["request"].transport_mode

    route_issues = check_route_closure(plan, hotel)
    record_route(route_issues)
    report = dict(plan.quality_report or {})
    existing_issues = list(report.get("issues", []))
    for issue in route_issues:
        if issue not in existing_issues:
            existing_issues.append(issue)
    report["issues"] = existing_issues
    report["passed"] = not existing_issues
    plan.quality_report = report
    record_quality(report)

    retry_count = state.get("retry_count", 0)
    if route_issues and retry_count < 3:
        record_retry("route", retry_count + 1, "；".join(route_issues[:5]))
        return {
            "plan": plan,
            "feedback": "路线闭环校验未通过：" + "；".join(route_issues[:5]),
            "retry_count": retry_count + 1,
        }

    return {"plan": plan}


def route_after_budget(state: AgentState) -> str:
    plan = state["plan"]
    report = plan.budget_report

    if report and not report.within_budget and state.get("retry_count", 0) < 3:
        return "replan"

    return "finish"


def route_after_quality(state: AgentState) -> str:
    report = state["plan"].quality_report or {}
    if not report.get("passed", True) and state.get("retry_count", 0) < 3:
        if state.get("invalid_days"):
            return "repair"
        return "replan"

    return "finish"


def route_after_surrounding(state: AgentState) -> str:
    report = state["plan"].quality_report or {}
    if not report.get("passed", True) and state.get("retry_count", 0) < 3:
        return "replan"

    return "finish"


workflow = StateGraph(AgentState)

workflow.add_node("analyze", instrument_node("analyze", analyze_node))
workflow.add_node("attractions", instrument_node("attractions", attraction_node))
workflow.add_node("foods", instrument_node("foods", food_node))
workflow.add_node("hotels", instrument_node("hotels", hotel_node))
workflow.add_node("weather", instrument_node("weather", weather_node))
workflow.add_node("itinerary", instrument_node("itinerary", itinerary_node))
workflow.add_node("budget", instrument_node("budget", budget_node))
workflow.add_node("quality", instrument_node("quality", quality_node))
workflow.add_node("repair_days", instrument_node("repair_days", repair_days_node))
workflow.add_node("surrounding", instrument_node("surrounding", surrounding_node))

workflow.add_edge(START, "analyze")
workflow.add_edge("analyze", "attractions")
workflow.add_edge("analyze", "foods")
workflow.add_edge("analyze", "hotels")
workflow.add_edge("analyze", "weather")
workflow.add_edge("attractions", "itinerary")
workflow.add_edge("foods", "itinerary")
workflow.add_edge("hotels", "itinerary")
workflow.add_edge("weather", "itinerary")
workflow.add_edge("itinerary", "budget")

workflow.add_conditional_edges(
    "budget",
    route_after_budget,
    {
        "replan": "itinerary",
        "finish": "quality",
    },
)

workflow.add_conditional_edges(
    "quality",
    route_after_quality,
    {
        "replan": "itinerary",
        "repair": "repair_days",
        "finish": "surrounding",
    },
)

workflow.add_edge("repair_days", "budget")

workflow.add_conditional_edges(
    "surrounding",
    route_after_surrounding,
    {
        "replan": "itinerary",
        "finish": END,
    },
)

trip_graph = workflow.compile(checkpointer=SyncMemorySaver())
