from app.schemas.trip import AttractionCandidate, TripRequest
from app.services.amap_client import search_attractions


def recommend_attractions(req: TripRequest, requirement: dict, count: int = 8) -> list[AttractionCandidate]:
    keywords = requirement.get("attraction_keywords", [])
    return search_attractions(req, keywords, limit=count)