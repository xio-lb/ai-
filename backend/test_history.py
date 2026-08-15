from app.schemas.trip import TripPlan
from app.services.history_service import delete_plan, get_plan, list_plans, save_plan

plan = TripPlan(
    destination="成都",
    days=1,
    budget=1000,
    preferences=["美食"],
    overview="测试行程",
    daily_plans=[],
    total_cost=500,
    notes=[],
    budget_report=None,
)

plan_id = save_plan(plan)
print("saved id:", plan_id)
print("list:", list_plans())

loaded = get_plan(plan_id)
print("loaded destination:", loaded.destination)

print("deleted:", delete_plan(plan_id))