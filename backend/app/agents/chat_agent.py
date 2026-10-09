import json

from app.services.deepseek_client import chat_json

SYSTEM_PROMPT = """你是AI旅行规划助手的对话顾问。你的任务是通过对话收集用户的旅行需求。

需要收集的信息：
- destination 目的地
- days 天数
- budget 总预算
- departure_city 出发城市
- travel_date 出发日期
- pace 节奏：relaxed/standard/compact
- hotel_budget 酒店预算
- preferences 偏好列表
- dietary_notes 饮食限制
- companions 出行人数

规则：
1. 每次最多问 1-2 个问题，语气自然。
2. 用户信息不足时，ready 为 false，trip_request 为 null。
3. 信息足够时，ready 为 true，并输出完整的 trip_request。
4. 没有的信息给合理默认值，并在 reply 中说明。
5. 只输出 JSON。
"""


def chat_requirement(messages: list[dict], memory: dict | None = None) -> dict:
    history = json.dumps(messages, ensure_ascii=False)

    memory_text = ""
    if memory:
        memory_text = f"""
用户已知记忆：
- 偏好：{memory.get('preferences', [])}
- 去过城市：{memory.get('visited_cities', [])}
- 饮食限制：{memory.get('dietary_notes', '')}
- 常用节奏：{memory.get('pace', '')}
- 常用交通：{memory.get('transport_mode', '')}
请复用这些信息，不要重复询问已经知道的内容。
"""

    user_prompt = f"""以下是用户和助手的对话历史，请继续对话，只输出 JSON：
{memory_text}
{history}

输出结构：
{{
  "reply": "你回复用户的话",
  "ready": false,
  "trip_request": null,
  "missing": ["还未收集的信息"]
}}
"""

    return chat_json(
        user_prompt,
        system_prompt=SYSTEM_PROMPT,
        prompt_name="chat_requirement",
    )
