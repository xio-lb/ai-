from app.schemas.trip import TripPlan, TripRequest


def test_trip_request_defaults():
    req = TripRequest(destination="成都", days=3, budget=3000)
    assert req.preferences == []
    assert req.pace == "standard"
    assert req.variant_theme == ""
    assert req.companions == 1


def test_trip_plan_roundtrip():
    plan = TripPlan(
        destination="成都",
        days=2,
        budget=2000,
        daily_plans=[],
        quality_report={"passed": True, "issues": []},
    )
    restored = TripPlan.model_validate(plan.model_dump())
    assert restored.quality_report["passed"] is True
    assert restored.user_preferences == []
    assert restored.dietary_notes == ""


def test_old_history_json_defaults():
    raw = '{"destination":"成都","days":2,"budget":2000,"daily_plans":[]}'
    plan = TripPlan.model_validate_json(raw)
    assert plan.quality_report == {}
    assert plan.dietary_notes == ""
    assert plan.companions == 1
    assert plan.variant_theme == ""