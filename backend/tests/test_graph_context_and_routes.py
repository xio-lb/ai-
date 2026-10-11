from app.agents import graph as graph_module
from app.services import context_cache
from app.schemas.trip import (
    AttractionCandidate,
    BudgetReport,
    DayPlan,
    FoodCandidate,
    HotelCandidate,
    RouteInfo,
    Spot,
    TripPlan,
    TripRequest,
)


def _candidate(name, location):
    return AttractionCandidate(name=name, location=location)


def _food(name, location):
    return FoodCandidate(name=name, location=location)


def test_graph_reuses_context_and_optimizes_route(monkeypatch):
    context_cache.reset_for_tests()
    calls = {"attractions": 0, "foods": 0, "hotels": 0, "weather": 0}

    def fake_requirement(request, instruction=None):
        return {
            "destination": request.destination,
            "days": request.days,
            "budget": request.budget,
            "preferences": request.preferences,
            "attraction_keywords": ["人文"],
            "food_keywords": ["本地菜"],
        }

    def fake_attractions(request, requirement, count=8):
        calls["attractions"] += 1
        return [
            _candidate("宽窄巷子", "104.055,30.669"),
            _candidate("武侯祠", "104.045,30.646"),
            _candidate("杜甫草堂", "104.028,30.660"),
        ]

    def fake_foods(request, requirement, count=8):
        calls["foods"] += 1
        return [_food("龙抄手", "104.080,30.653")]

    def fake_hotels(request, count=6):
        calls["hotels"] += 1
        return [HotelCandidate(name="成都酒店", location="104.070,30.660")]

    def fake_weather(city, travel_date=""):
        calls["weather"] += 1
        from app.schemas.trip import WeatherInfo

        return WeatherInfo(city=city, weather="晴", travel_date=travel_date)

    def fake_plan(**kwargs):
        return TripPlan(
            destination="成都",
            days=1,
            budget=2000,
            daily_plans=[
                DayPlan(
                    day=1,
                    theme="市区",
                    spots=[
                        Spot(name="宽窄巷子", location="104.055,30.669"),
                        Spot(name="武侯祠", location="104.045,30.646"),
                        Spot(name="杜甫草堂", location="104.028,30.660"),
                    ],
                    foods=[_food("龙抄手", "104.080,30.653")],
                )
            ],
            total_cost=1500,
        )

    def fake_budget(plan):
        # Budget validation normally calls the LLM; keep this test offline and
        # deterministic so CI never depends on a real DeepSeek key.
        return BudgetReport(
            budget=plan.budget,
            total_cost=plan.total_cost,
            within_budget=plan.total_cost <= plan.budget,
            savings=plan.budget - plan.total_cost,
            suggestions=[],
        )

    def fake_nearby(location, types="", radius=0, limit=0):
        return []

    def fake_legs(plan, hotel, mode):
        return [
            RouteInfo(
                day=1,
                from_name=hotel.name,
                to_name=spot.name,
                stop_type="spot",
                polyline="1,1;2,2",
            )
            for spot in plan.daily_plans[0].spots
        ] + [
            RouteInfo(
                day=1,
                from_name=plan.daily_plans[0].spots[-1].name,
                to_name=hotel.name,
                stop_type="hotel",
                polyline="2,2;1,1",
            )
        ]

    monkeypatch.setattr(graph_module, "analyze_requirement", fake_requirement)
    monkeypatch.setattr(graph_module, "recommend_attractions", fake_attractions)
    monkeypatch.setattr(graph_module, "recommend_foods", fake_foods)
    monkeypatch.setattr(graph_module, "recommend_hotels", fake_hotels)
    monkeypatch.setattr(graph_module, "fetch_weather", fake_weather)
    monkeypatch.setattr(graph_module, "generate_trip_plan", fake_plan)
    monkeypatch.setattr(graph_module, "validate_budget", fake_budget)
    monkeypatch.setattr(graph_module, "search_nearby_pois", fake_nearby)
    monkeypatch.setattr(graph_module, "build_route_legs", fake_legs)

    observed = {"reuse": [], "optimized": []}

    def record_reuse(kind, hit):
        observed["reuse"].append((kind, hit))

    def record_optimization(*args):
        observed["optimized"].append(args)

    monkeypatch.setattr(graph_module, "record_context_reuse", record_reuse)
    monkeypatch.setattr(graph_module, "record_route_optimization", record_optimization)

    request = TripRequest(destination="成都", days=1, budget=2000, travel_date="2026-10-10")
    config = {"configurable": {"thread_id": "trip-test"}}

    first = graph_module.trip_graph.invoke({"request": request}, config=config, durability="sync")
    second = graph_module.trip_graph.invoke({"request": request}, config=config, durability="sync")

    assert first["plan"].route_optimization
    assert second["plan"].route_optimization
    assert calls == {"attractions": 1, "foods": 1, "hotels": 1, "weather": 1}
    assert observed["reuse"]
    assert any(hit for kind, hit in observed["reuse"] if kind == "attractions")
    assert observed["optimized"]
