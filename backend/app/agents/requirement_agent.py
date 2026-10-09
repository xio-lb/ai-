from app.schemas.trip import TripRequest
from app.services.deepseek_client import chat_json

SYSTEM_PROMPT = "你是旅行需求分析专家，只输出 JSON。"


def analyze_requirement(req: TripRequest, instruction: str | None = None) -> dict:
    instruction_text = ""
    if instruction:
        instruction_text = f"""
用户补充要求：{instruction}
请结合补充要求重新生成 attraction_keywords 和 food_keywords。
"""

    theme_text = ""
    if req.variant_theme:
        theme_text = f"""
本次候选方案主题：{req.variant_theme}
请让 attraction_keywords 和 food_keywords 重点围绕该主题，并在 travel_style 中写明该主题。
"""

    user_prompt = f"""请分析以下旅行需求，只输出 JSON：

目的地：{req.destination}
天数：{req.days}天
预算：{req.budget}元
偏好：{req.preferences}
节奏：{req.pace}（紧凑 / 标准 / 舒适）
{theme_text}
{instruction_text}
输出结构：
{{
  "destination": "目的地",
  "days": 天数,
  "budget": 预算,
  "preferences": ["偏好"],
  "travel_style": "{req.variant_theme or '本次旅行主题'}",
  "pacing": "结合 req.pace 的节奏建议",
  "key_highlights": ["亮点1", "亮点2"],
  "special_notes": ["注意事项"],
  "attraction_keywords": ["具体景点名1", "具体景点名2", "具体景点名3", "具体景点名4"],
  "food_keywords": ["具体餐厅或美食名1", "具体餐厅或美食名2", "具体餐厅或美食名3", "具体餐厅或美食名4"]
}}

attraction_keywords 和 food_keywords 必须是该城市可能真实存在的具体名称，用于高德地图搜索。
"""

    return chat_json(
        user_prompt,
        system_prompt=SYSTEM_PROMPT,
        prompt_name="requirement_analyze",
    )
