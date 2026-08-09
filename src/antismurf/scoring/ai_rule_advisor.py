"""AI-assisted rule authoring via OpenAI-compatible chat completions.

Users provide an API key (DeepSeek / Kimi / OpenAI / OpenRouter, etc.),
describe the rule in natural language, and the assistant returns an
ExpressionRule JSON array which is validated before being applied.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from antismurf.config.expression_rules_io import expression_rule_from_dict
from antismurf.config.settings import ExpressionRule
from antismurf.scoring.expression_engine import (
    ARITHMETIC_LABELS,
    OPERATOR_LABELS,
    OPERATORS,
    VARIABLE_CATALOG,
)
from antismurf.scoring.rule_pack import validate_rules

logger = logging.getLogger(__name__)


def _variable_table() -> str:
    return "\n".join(f"- `{vid}`：{desc}" for vid, desc in VARIABLE_CATALOG.items())


def build_rules_prompt(requirement: str) -> str:
    """Build the user prompt: variable table, operators, output format."""
    op_table = "、".join(
        f"{op}（{OPERATOR_LABELS.get(op, op)}）" for op in OPERATORS
    )
    arith_table = "、".join(
        f"{symbol}（{label}）" for symbol, label in ARITHMETIC_LABELS.items()
    )
    return f"""请根据以下需求生成 AntiSmurf 评分规则(凯瑞甘生存2 防炸鱼)。

## 可用变量
{_variable_table()}

## 比较运算符
{op_table}

## 算术运算符(可选,作用于左侧变量)
{arith_table}

## 规则字段
- id: 唯一英文标识(必填)
- label: 中文说明
- left: 变量名(必填)
- arith_op: 可选算术运算符(+ - * /)
- middle: 算术右值(数字)
- op: 比较运算符
- right: 比较右值(数字或变量名)
- right2: between 运算符时的上界
- weight: 命中时嫌疑分增量(正数加嫌疑)
- else_weight: 未命中时增量(可为 0)
- min_games: 至少对局数(0 为不限)

## 输出要求
只输出一个 JSON 数组,不要任何解释,不要 Markdown 代码块。
每个规则对象包含上述字段,left/op/right/weight 必填。

## 用户需求
{requirement}
"""


async def request_rules(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    *,
    timeout_sec: float = 60.0,
) -> str:
    """Call the OpenAI-compatible chat completions endpoint."""
    if not api_key.strip():
        raise ValueError("未填写 API Key")
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model.strip() or "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是 AntiSmurf 评分规则编写助手,只输出 JSON 数组,不要任何解释。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("AI 响应中没有 choices")
    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("AI 返回内容为空")
    return content


def parse_ai_rules_response(text: str) -> list[ExpressionRule]:
    """Parse and validate the AI-returned rules JSON array."""
    raw = _extract_json(text)
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("rules") or raw.get("expression_rules") or []
    else:
        raise ValueError("AI 返回内容不是 JSON 数组")

    rules: list[ExpressionRule] = []
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            rules.append(expression_rule_from_dict(item))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    if not rules:
        detail = f"（解析错误: {'; '.join(errors[:3]) or '无规则对象'}）"
        raise ValueError(f"AI 未返回任何可解析的规则 {detail}")

    result = validate_rules(rules)
    if result.errors:
        logger.warning("AI 规则校验问题: %s", "; ".join(result.errors[:5]))
    return rules


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError("无法从 AI 响应中提取 JSON")
