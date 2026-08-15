from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.attraction_agent import recommend_attractions
from app.agents.budget_agent import validate_budget
from app.agents.food_agent import recommend_foods
from app.agents.hotel_agent import recommend_hotels
from app.agents.itinerary_agent import generate_trip_plan
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


def analyze_node(state: AgentState) -> dict:
    report_progress("正在解析行程需求")

    return {
        "requirement": analyze_requirement(
            state["request"],
            instruction=state.get("instruction"),
        )
    }


def attraction_node(state: AgentState) -> dict:
    report_progress("正在筛选景点")

    return {
        "attractions": recommend_attractions(
            state["request"],
            state["requirement"],
            count=8,
        )
    }


def food_node(state: AgentState) -> dict:
    report_progress("正在筛选美食")

    return {
        "foods": recommend_foods(
            state["request"],
            state["requirement"],
            count=8,
        )
    }


def hotel_node(state: AgentState) -> dict:
    report_progress("正在筛选酒店")

    return {"hotels": recommend_hotels(state["request"], count=6)}


def weather_node(state: AgentState) -> dict:
    report_progress("正在获取天气")

    return {"weather": fetch_weather(state["request"].destination, state["request"].travel_date)}


def itinerary_node(state: AgentState) -> dict:
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
    )
    return {"plan": plan}


def budget_node(state: AgentState) -> dict:
    report_progress("正在核算预算")

    plan = state["plan"]
    report = validate_budget(plan)
    plan.budget_report = report
    retry_count = state.get("retry_count", 0)

    if not report.within_budget and retry_count < 3:
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
    report_progress("正在校验行程质量")

    plan = state["plan"]
    report = check_quality(
        plan,
        state.get("attractions", []),
        state.get("foods", []),
        state.get("hotels", []),
    )
    plan.quality_report = report
    retry_count = state.get("retry_count", 0)

    if not report["passed"] and retry_count < 3:
        return {
            "plan": plan,
            "feedback": "质量校验未通过：" + "；".join(report["issues"][:5]),
            "retry_count": retry_count + 1,
        }

    return {"plan": plan, "feedback": None, "retry_count": retry_count}


def surrounding_node(state: AgentState) -> dict:
    report_progress("正在补充周边与路线")

    plan = state["plan"]
    hotels = state.get("hotels", [])
    hotel = hotels[0] if hotels else None
    nearby: list[NearbyPoi] = []
    routes: dict[str, RouteInfo] = {}
    legs: list[RouteInfo] = []

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
    plan.transport_mode = state["request"].transport_mode

    route_issues = check_route_closure(plan, hotel)
    report = dict(plan.quality_report or {})
    existing_issues = list(report.get("issues", []))
    for issue in route_issues:
        if issue not in existing_issues:
            existing_issues.append(issue)
    report["issues"] = existing_issues
    report["passed"] = not existing_issues
    plan.quality_report = report

    retry_count = state.get("retry_count", 0)
    if route_issues and retry_count < 3:
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
        return "replan"

    return "finish"


def route_after_surrounding(state: AgentState) -> str:
    report = state["plan"].quality_report or {}
    if not report.get("passed", True) and state.get("retry_count", 0) < 3:
        return "replan"

    return "finish"


workflow = StateGraph(AgentState)

workflow.add_node("analyze", analyze_node)
workflow.add_node("attractions", attraction_node)
workflow.add_node("foods", food_node)
workflow.add_node("hotels", hotel_node)
workflow.add_node("weather", weather_node)
workflow.add_node("itinerary", itinerary_node)
workflow.add_node("budget", budget_node)
workflow.add_node("quality", quality_node)
workflow.add_node("surrounding", surrounding_node)

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
        "finish": "surrounding",
    },
)

workflow.add_conditional_edges(
    "surrounding",
    route_after_surrounding,
    {
        "replan": "itinerary",
        "finish": END,
    },
)

trip_graph = workflow.compile()
