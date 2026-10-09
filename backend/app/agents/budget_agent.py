import re

from app.schemas.trip import (
    ActualExpense,
    BudgetCategoryDetail,
    BudgetCategoryItem,
    BudgetDayDetail,
    BudgetDetail,
    BudgetReport,
    TripPlan,
)
from app.services.deepseek_client import chat_json

SYSTEM_PROMPT = "你是预算审核专家，只输出 JSON。"

CATEGORY_LABELS = ["门票", "餐饮", "住宿", "交通"]


def _parse_amount(text: str) -> int:
    values = [int(value) for value in re.findall(r"\d+", text or "")]
    if not values:
        return 0
    if len(values) >= 2:
        return (min(values) + max(values)) // 2
    return values[0]


def _item_amount(text: str, fallback: int) -> int:
    parsed = _parse_amount(text)
    return parsed if parsed > 0 else fallback


def _scale_amounts(amounts: list[int], total: int) -> list[int]:
    if not amounts:
        return []
    raw_sum = sum(max(0, amount) for amount in amounts)
    if raw_sum <= 0:
        base = total // len(amounts)
        result = [base] * len(amounts)
        for index in range(total % len(amounts)):
            result[index] += 1
        return result

    scaled = [max(0, round(max(0, amount) * total / raw_sum)) for amount in amounts]
    diff = total - sum(scaled)
    if diff > 0:
        for index in range(diff):
            scaled[index % len(scaled)] += 1
    elif diff < 0:
        for index in range(-diff):
            target = index % len(scaled)
            if scaled[target] > 0:
                scaled[target] -= 1
    return scaled


def _normalize_detail(plan: TripPlan, raw: dict | None) -> BudgetDetail:
    total = max(0, plan.total_cost or 0)
    raw_days = (raw or {}).get("days") or []
    raw_categories = (raw or {}).get("categories") or []

    raw_day_map: dict[int, BudgetDayDetail] = {}
    for item in raw_days:
        day_number = int(item.get("day", 0))
        categories = {
            str(key): max(0, int(value or 0))
            for key, value in (item.get("categories") or {}).items()
        }
        raw_day_map[day_number] = BudgetDayDetail(
            day=day_number,
            amount=max(0, int(item.get("amount", 0) or 0)),
            min_amount=max(0, int(item.get("min_amount", 0) or 0)),
            max_amount=max(0, int(item.get("max_amount", 0) or 0)),
            typical=max(0, int(item.get("typical", 0) or 0)),
            categories=categories,
        )

    days: list[BudgetDayDetail] = []
    for day in plan.daily_plans:
        if day.day in raw_day_map:
            detail = raw_day_map[day.day]
        else:
            food_cost = sum(_item_amount(food.price_range, 30) for food in day.foods)
            ticket_cost = len(day.spots) * 35
            transport_cost = len(day.spots) * 15 + 20
            hotel_hint = _parse_amount(plan.hotels[0].price_hint) if plan.hotels else 0
            hotel_cost = round(
                (hotel_hint or plan.budget * 0.22) / max(1, len(plan.daily_plans))
            )
            detail = BudgetDayDetail(
                day=day.day,
                amount=food_cost + ticket_cost + transport_cost + hotel_cost,
                typical=food_cost + ticket_cost + transport_cost + hotel_cost,
                categories={
                    "门票": ticket_cost,
                    "餐饮": food_cost,
                    "住宿": hotel_cost,
                    "交通": transport_cost,
                },
            )
        days.append(detail)

    if not days:
        days = [
            BudgetDayDetail(
                day=1,
                amount=total,
                min_amount=round(total * 0.75),
                max_amount=round(total * 1.3),
                typical=total,
                categories={"门票": 0, "餐饮": 0, "住宿": 0, "交通": 0},
            )
        ]

    day_typicals = [day.typical or day.amount for day in days]
    if sum(day_typicals) <= 0:
        base = total // len(days)
        day_typicals = [
            base + (1 if index < total % len(days) else 0)
            for index in range(len(days))
        ]
    scaled_days = _scale_amounts(day_typicals, total)
    for index, day in enumerate(days):
        typical = scaled_days[index]
        day.amount = typical
        day.typical = typical
        day.min_amount = max(0, day.min_amount or round(typical * 0.75))
        day.max_amount = max(day.min_amount, day.max_amount or round(typical * 1.3))

    category_map: dict[str, dict] = {
        label: {
            "min_amount": 0,
            "max_amount": 0,
            "typical": 0,
            "note": "",
            "items": [],
        }
        for label in CATEGORY_LABELS
    }
    for item in raw_categories:
        name = str(item.get("category", ""))
        if name not in category_map:
            category_map[name] = {
                "min_amount": 0,
                "max_amount": 0,
                "typical": 0,
                "note": "",
                "items": [],
            }
        category_map[name]["min_amount"] = max(0, int(item.get("min_amount", 0) or 0))
        category_map[name]["max_amount"] = max(0, int(item.get("max_amount", 0) or 0))
        category_map[name]["typical"] = max(
            0,
            int(item.get("typical", 0) or 0)
            or int(item.get("amount", 0) or 0),
        )
        category_map[name]["note"] = str(item.get("note", "") or "")
        for raw_item in item.get("items") or []:
            category_map[name]["items"].append(
                BudgetCategoryItem(
                    name=str(raw_item.get("name", "")),
                    amount=max(0, int(raw_item.get("amount", 0) or 0)),
                )
            )

    extra_labels = [name for name in category_map if name not in CATEGORY_LABELS]
    all_labels = CATEGORY_LABELS + extra_labels

    for label in all_labels:
        if category_map[label]["typical"] <= 0:
            category_map[label]["typical"] = sum(
                int(day.categories.get(label, 0) or 0) for day in days
            )

    if sum(category_map[label]["typical"] for label in CATEGORY_LABELS) <= 0:
        for label, ratio in zip(CATEGORY_LABELS, [0.35, 0.35, 0.2, 0.1]):
            category_map[label]["typical"] = round(total * ratio)

    category_typicals = [
        category_map[label]["typical"] for label in all_labels
    ]
    scaled_categories = _scale_amounts(category_typicals, total)
    categories: list[BudgetCategoryDetail] = []

    for index, label in enumerate(all_labels):
        typical = scaled_categories[index]
        min_amount = max(0, category_map[label]["min_amount"] or round(typical * 0.75))
        max_amount = max(
            min_amount,
            category_map[label]["max_amount"] or round(typical * 1.3),
        )
        items = category_map[label]["items"]
        item_sum = sum(item.amount for item in items)
        if items and item_sum > 0:
            scaled_items = _scale_amounts([item.amount for item in items], typical)
            for item_index, item in enumerate(items):
                item.amount = scaled_items[item_index]
        categories.append(
            BudgetCategoryDetail(
                category=label,
                amount=typical,
                min_amount=min_amount,
                max_amount=max_amount,
                typical=typical,
                note=category_map[label]["note"],
                items=items,
            )
        )

    existing_actuals = (
        list(plan.budget_detail.actual_expenses) if plan.budget_detail else []
    )
    existing_category_names = {category.category for category in categories}
    for expense in existing_actuals:
        if expense.category and expense.category not in existing_category_names:
            categories.append(
                BudgetCategoryDetail(
                    category=expense.category,
                    amount=0,
                    min_amount=0,
                    max_amount=0,
                    typical=0,
                    note="自定义花费项目",
                    items=[],
                )
            )
            existing_category_names.add(expense.category)
    return BudgetDetail(
        total_cost=total,
        budget=plan.budget,
        days=days,
        categories=categories,
        actual_expenses=[ActualExpense.model_validate(item) for item in existing_actuals],
    )


def validate_budget(plan: TripPlan) -> BudgetReport:
    user_prompt = f"""请审核以下行程的预算，只输出 JSON。

行程预算：{plan.budget} 元
行程总花费：{plan.total_cost} 元
每日安排：
{plan.model_dump_json(indent=2, ensure_ascii=False)}

输出格式：
{{
  "budget": {plan.budget},
  "total_cost": {plan.total_cost},
  "within_budget": true,
  "savings": {plan.budget - plan.total_cost},
  "suggestions": ["预算内", "可以再节省的具体建议"],
  "detail": {{
    "days": [
      {{
        "day": 1,
        "min_amount": 200,
        "max_amount": 360,
        "typical": 280,
        "categories": {{"门票": 100, "餐饮": 80, "住宿": 60, "交通": 60}}
      }}
    ],
    "categories": [
      {{"category": "门票", "min_amount": 60, "max_amount": 180, "typical": 120, "note": "按景点数量和淡旺季浮动"}},
      {{"category": "餐饮", "min_amount": 120, "max_amount": 260, "typical": 180, "note": "按人数和餐厅档次浮动"}},
      {{"category": "住宿", "min_amount": 120, "max_amount": 260, "typical": 180, "note": "节假日可能明显上涨"}},
      {{"category": "交通", "min_amount": 40, "max_amount": 160, "typical": 90, "note": "公交与打车差异较大"}}
    ]
  }}
}}

要求：
1. detail.days 覆盖行程中的每一天，typical 表示当天参考花费，min_amount / max_amount 表示合理浮动区间。
2. detail.categories 必须包含 门票 / 餐饮 / 住宿 / 交通，同样使用 min_amount / max_amount / typical；如行程有明显购物、纪念品、特产、小吃、拍照、演出等支出，可补充这些类别。
3. detail.days 的 typical 之和与 detail.categories 的 typical 之和都必须约等于 total_cost。
4. 不要给出单个景点、单顿饭或具体酒店的固定价格，只给类别区间和波动原因。
"""

    data = chat_json(
        user_prompt,
        system_prompt=SYSTEM_PROMPT,
        prompt_name="budget_validate",
    )
    report_data = {
        key: data.get(key)
        for key in ("budget", "total_cost", "within_budget", "savings", "suggestions")
    }
    report = BudgetReport.model_validate(report_data)

    corrected = report.model_copy(
        update={
            "budget": plan.budget,
            "total_cost": plan.total_cost,
            "within_budget": plan.total_cost <= plan.budget,
            "savings": plan.budget - plan.total_cost,
        }
    )
    plan.budget_detail = _normalize_detail(plan, data.get("detail"))
    return corrected
