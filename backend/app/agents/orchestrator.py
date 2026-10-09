import uuid

from app.agents.adjust_agent import apply_precise_adjust
from app.agents.graph import trip_graph
from app.schemas.trip import TripPlan, TripRequest
from app.services.memory_service import get_user_memory
from app.services.observability import trace_generation


def plan_trip(
    req: TripRequest,
    source: str = "api",
    request_id: str | None = None,
    variant_theme: str = "",
) -> TripPlan:
    with trace_generation(
        source=source,
        request=req,
        request_id=request_id,
        variant_theme=variant_theme,
    ) as trace:
        result = trip_graph.invoke({"request": req})
        plan = result["plan"]
        plan.user_preferences = list(req.preferences or [])
        plan.departure_city = req.departure_city
        plan.dietary_notes = req.dietary_notes
        plan.hotel_budget = req.hotel_budget
        plan.companions = req.companions
        plan.user_memory = get_user_memory()
        trace.attach_plan(plan)
        return plan


VARIANT_THEMES = [
    {
        "id": "culture",
        "label": "人文深度",
        "pace": "standard",
        "style": "优先博物馆、历史街区、文化场馆与古迹，人文讲解和沉浸体验多一些",
        "preference": "人文历史、博物馆、文化街区",
    },
    {
        "id": "food",
        "label": "美食探店",
        "pace": "compact",
        "style": "优先本地特色餐厅、小吃街与美食地标，行程穿插觅食，餐饮权重更高",
        "preference": "美食探店、地道小吃、本地特色",
    },
    {
        "id": "nature",
        "label": "自然休闲",
        "pace": "relaxed",
        "style": "优先公园、山水、户外自然景区，节奏放慢，预留休息和自由活动",
        "preference": "自然风光、公园、户外休闲",
    },
    {
        "id": "family",
        "label": "亲子轻松",
        "pace": "relaxed",
        "style": "优先亲子友好、乐园、动物园、植物园与轻松互动体验",
        "preference": "亲子友好、乐园、轻松互动",
    },
    {
        "id": "budget",
        "label": "经济优选",
        "pace": "compact",
        "style": "优先免费或低价景点与平价餐厅，控制花销，减少高消费项目",
        "preference": "经济实惠、免费景点、平价美食",
    },
]

_THEME_BY_ID = {theme["id"]: theme for theme in VARIANT_THEMES}

_FAMILY_HINTS = ("亲子", "儿童", "乐园", "小朋友", "遛娃")
_BUDGET_HINTS = ("经济", "省钱", "穷游", "性价比")
_ORDER_HINTS = {
    "culture": ("人文", "历史", "博物馆", "文化"),
    "food": ("美食", "小吃", "探店", "吃"),
    "nature": ("自然", "公园", "山水", "户外"),
}


def pick_variant_themes(req: TripRequest) -> list[dict]:
    theme_ids = ["culture", "food", "nature"]
    preference_text = "".join(req.preferences or [])

    if any(hint in preference_text for hint in _FAMILY_HINTS):
        theme_ids[2] = "family"
    elif any(hint in preference_text for hint in _BUDGET_HINTS):
        theme_ids[2] = "budget"

    def order_score(theme_id: str) -> int:
        hints = _ORDER_HINTS.get(theme_id, ())
        positions = [preference_text.find(hint) for hint in hints if hint in preference_text]
        return min(positions) if positions else len(preference_text) + 1

    theme_ids.sort(key=order_score)
    return [_THEME_BY_ID[theme_id] for theme_id in theme_ids]


def build_variant_plan(
    req: TripRequest, theme: dict, request_id: str | None = None
) -> TripPlan:
    variant_preferences = list(req.preferences or [])
    variant_preferences.append(f"{theme['label']}：{theme['style']}")
    variant_req = req.model_copy(
        update={
            "pace": theme["pace"],
            "variant_theme": theme["label"],
            "preferences": variant_preferences,
        }
    )
    plan = plan_trip(
        variant_req,
        source="variant",
        request_id=request_id,
        variant_theme=theme["label"],
    )
    plan.variant_label = theme["label"]
    plan.variant_pace = theme["pace"]
    plan.variant_theme = theme["label"]
    return plan


def plan_variants(req: TripRequest) -> list[TripPlan]:
    request_id = uuid.uuid4().hex
    return [
        build_variant_plan(req, theme, request_id=request_id)
        for theme in pick_variant_themes(req)
    ]


def adjust_trip(current_plan: TripPlan, user_message: str) -> TripPlan:
    precise = apply_precise_adjust(current_plan, user_message)
    if precise is not None:
        return precise

    req = TripRequest(
        destination=current_plan.destination,
        days=current_plan.days,
        budget=current_plan.budget,
        preferences=current_plan.preferences,
        travel_date=current_plan.weather.travel_date if current_plan.weather else "",
        pace=current_plan.variant_pace or "standard",
        variant_theme=current_plan.variant_theme or "",
        transport_mode=current_plan.transport_mode or "auto",
    )

    with trace_generation(source="adjust", request=req) as trace:
        result = trip_graph.invoke(
            {
                "request": req,
                "instruction": user_message,
                "current_plan": current_plan,
            }
        )
        plan = result["plan"]
        trace.attach_plan(plan)
        return plan
