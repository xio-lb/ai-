import json

from app.schemas.trip import TripPlan
from app.services.deepseek_client import chat_json
from app.services.prompt_builder import build_trip_prompt

prompt = build_trip_prompt(
    destination="成都",
    days=3,
    budget=3000,
    preferences=["美食", "人文"],
)

data = chat_json(
    prompt,
    system_prompt="你是专业旅行规划师，只输出符合要求的 JSON。",
)

try:
    plan = TripPlan.model_validate(data)
except Exception:
    print("校验失败，模型返回的原始数据是：")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    raise

print(plan.model_dump_json(indent=2, ensure_ascii=False))