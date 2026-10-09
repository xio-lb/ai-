from app.agents.graph import quality_node, route_after_quality
from app.agents.quality_agent import check_quality, check_route_closure
from app.schemas.trip import (
    AttractionCandidate,
    DayPlan,
    FoodCandidate,
    HotelCandidate,
    RouteInfo,
    Spot,
    TripPlan,
)


def _plan(spots, foods=None):
    return TripPlan(
        destination="成都",
        days=1,
        budget=1000,
        daily_plans=[DayPlan(day=1, theme="市区", spots=spots, foods=foods or [])],
    )


def test_quality_rejects_unknown_candidates():
    plan = _plan([Spot(name="不存在的景点", location="0,0")])
    report = check_quality(plan, [], [], [])
    assert report["passed"] is False
    assert any("不在候选清单" in issue for issue in report["issues"])


def test_quality_repairs_missing_location():
    attractions = [AttractionCandidate(name="宽窄巷子", location="104.06,30.67")]
    foods = [FoodCandidate(name="龙抄手", location="104.07,30.66")]
    plan = _plan(
        [
            Spot(name="宽窄巷子"),
            Spot(name="宽窄巷子", location="104.06,30.67"),
        ],
        [FoodCandidate(name="龙抄手")],
    )
    report = check_quality(plan, attractions, foods, [])
    assert report["passed"] is True
    assert any("修复" in item for item in report["repairs"])


def test_route_closure_requires_return():
    plan = _plan([Spot(name="宽窄巷子", location="104.06,30.67")])
    hotel = HotelCandidate(name="酒店", location="104.05,30.65")
    plan.route_legs = [
        RouteInfo(
            mode="driving",
            day=1,
            from_name="酒店",
            to_name="宽窄巷子",
            stop_type="spot",
            polyline="104.05,30.65;104.06,30.67",
        )
    ]
    issues = check_route_closure(plan, hotel)
    assert any("没有返回酒店" in issue for issue in issues)


def test_quality_node_retries():
    plan = _plan([Spot(name="不存在的景点")])
    state = {
        "plan": plan,
        "attractions": [],
        "foods": [],
        "hotels": [],
        "retry_count": 0,
    }
    result = quality_node(state)
    assert result["retry_count"] == 1
    assert "质量校验未通过" in result["feedback"]
    assert result["invalid_days"] == [1]
    assert route_after_quality({**state, **result}) == "repair"


def test_quality_routes_to_full_replan_without_day_scope():
    plan = _plan([Spot(name="宽窄巷子", location="104.06,30.67")])
    plan.days = 2
    state = {
        "plan": plan,
        "attractions": [],
        "foods": [],
        "hotels": [],
        "retry_count": 0,
    }
    result = quality_node(state)
    assert "天数不匹配" in "；".join(result["plan"].quality_report["issues"])
    assert result["invalid_days"] == []
    assert route_after_quality({**state, **result}) == "replan"
