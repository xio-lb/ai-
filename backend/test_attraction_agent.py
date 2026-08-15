from app.agents.attraction_agent import recommend_attractions
from app.agents.requirement_agent import analyze_requirement
from app.schemas.trip import TripRequest

req = TripRequest(
    destination="成都",
    days=3,
    budget=3000,
    preferences=["美食", "人文"],
)

requirement = analyze_requirement(req)
attractions = recommend_attractions(req, requirement, count=6)

for item in attractions:
    print(f"{item.name} | {item.category} | {item.duration} | {item.location}")