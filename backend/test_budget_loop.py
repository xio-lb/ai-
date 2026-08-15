from app.agents.orchestrator import plan_trip
from app.schemas.trip import TripRequest

req = TripRequest(destination="成都", days=3, budget=800, preferences=["美食"])
plan = plan_trip(req)
print(plan.budget_report.model_dump_json(indent=2, ensure_ascii=False))