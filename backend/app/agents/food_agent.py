from app.schemas.trip import FoodCandidate, TripRequest
from app.services.amap_client import search_foods


def recommend_foods(req: TripRequest, requirement: dict, count: int = 8) -> list[FoodCandidate]:
    keywords = requirement.get("food_keywords", [])
    return search_foods(req, keywords, limit=count)