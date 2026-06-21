"""DeepSeek AI client for generating quiz distractors."""

import asyncio
import json
import logging
import httpx
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

_SHARED_CLIENT: Optional[httpx.AsyncClient] = None
_SEMAPHORE = asyncio.Semaphore(10)  # Max 10 concurrent AI requests

# System prompt for generating near-synonym distractors
_SYSTEM_PROMPT = """你是一个英语学习助手。用户会给你一个英语短语和它的中文释义。
请生成3个与正确释义意思相近但不同的中文干扰项，用于选择题。

要求：
1. 每个干扰项2-6个汉字
2. 必须是常见、自然的中文表达
3. 与正确答案意思相近但不相同（让学生需要仔细区分）
4. 3个干扰项之间也要互不相同
5. 不要使用正确答案本身或其子串

直接返回JSON数组，不要任何其他文字。示例：
["促进", "阻碍", "导致"]"""

_USER_TEMPLATE = """短语：{phrase}
正确释义：{meaning}
请生成3个近义干扰项："""

# System prompt for generating similar English phrase distractors
_PHRASE_SYSTEM_PROMPT = """你是一个英语学习助手。用户会给你一个英语短语和它的中文释义。
请生成3个在形式或用法上容易混淆的英语短语干扰项，用于选择题。

要求：
1. 每个干扰项必须是真实的英语短语
2. 与正确短语在用词或结构上有相似之处（如共享某个单词）
3. 语义上与正确答案不同
4. 3个干扰项之间互不相同
5. 不要使用正确答案本身

直接返回JSON数组，不要任何其他文字。示例：
["break down", "break up", "break through"]"""

_PHRASE_USER_TEMPLATE = """短语：{phrase}
释义：{meaning}
请生成3个容易混淆的英语短语干扰项："""

_WORD_ENRICHMENT_SYSTEM_PROMPT = """你是一个英语学习助手。用户会给你一组英语单词、词性、中文释义和例句。
请为每个单词生成精简学习拓展，用于小程序单词卡片。

要求：
1. usage_note 用中文，最多35个汉字，说明常见用法或搭配
2. context_meanings 最多2条，每条包含 context、meaning、example
3. context 用中文短场景标签，如“电话沟通”“邮件表达”“酒店场景”；meaning 用中文，example 用英文短句
4. 不要编造冷僻含义，优先常见生活语境
5. 直接返回JSON对象，key为单词本身，不要任何其他文字

示例：
{
  "brew": {
    "usage_note": "常用于冲泡饮品，也可表示酝酿。",
    "context_meanings": [
      {"context": "饮品场景", "meaning": "冲泡咖啡或茶", "example": "She brews tea every morning."},
      {"context": "抽象表达", "meaning": "计划正在形成", "example": "A plan is brewing."}
    ]
  }
}"""

_WORD_ENRICHMENT_USER_TEMPLATE = """请补全这些单词的学习拓展：
{words_json}"""

_HARD_DISTRACTOR_SYSTEM_PROMPT = """你是一个英语学习测验出题助手。请为选择题生成3个“适中偏难”的干扰项。

要求：
1. 干扰项要和正确答案处在相同语义场景、词性、搭配或表达结构中，让学习者需要认真区分
2. 干扰项必须和正确答案不同，不能包含正确答案，也不能只是正确答案的同义复述
3. 如果 target_language 是 zh，只返回自然中文；如果是 en，只返回自然英文
4. 优先生成常见、真实、适合口语学习的选项，不要冷僻或明显无关
5. 直接返回JSON数组，不要解释，不要Markdown

示例：
["确认预订", "更改行程", "办理入住"]"""

_HARD_DISTRACTOR_USER_TEMPLATE = """题型：{question_type}
目标语言：{target_language}
题干：{prompt}
学习项：{item_text}
正确答案：{correct}
中文释义：{meaning}
词性：{part_of_speech}
例句：{example}
可参考但不要照抄的候选池：{candidates_json}

请生成3个有挑战但可区分的干扰项："""


def _get_client() -> httpx.AsyncClient:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None or _SHARED_CLIENT.is_closed:
        _SHARED_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _SHARED_CLIENT


async def _call_deepseek(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 100,
    read_timeout: float = 8.0,
) -> Optional[str]:
    """Make a rate-limited DeepSeek API call. Returns response content or None."""
    settings = get_settings()
    api_key = getattr(settings, "DEEPSEEK_API_KEY", "")
    api_url = getattr(settings, "DEEPSEEK_API_URL", "https://api.deepseek.com/v1")

    if not api_key:
        return None

    async with _SEMAPHORE:
        try:
            client = _get_client()
            response = await client.post(
                f"{api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-v4-flash",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.8,
                    "max_tokens": max_tokens,
                },
                timeout=httpx.Timeout(connect=5.0, read=read_timeout, write=5.0, pool=5.0),
            )

            if response.status_code != 200:
                logger.warning("DeepSeek API returned status %d: %s", response.status_code, response.text[:200])
                return None

            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning("DeepSeek API connection error: %s", e)
            return None
        except (KeyError, IndexError) as e:
            logger.warning("DeepSeek API response parse error: %s", e)
            return None
        except Exception as e:
            logger.warning("DeepSeek API unexpected error: %s", e)
            return None


def _parse_json_array(content: str, count: int) -> Optional[list[str]]:
    """Parse a JSON array from DeepSeek response content."""
    if content is None:
        return None
    try:
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        distractors = json.loads(content)

        if not isinstance(distractors, list) or len(distractors) < count:
            return None

        return [d.strip() for d in distractors if d.strip()][:count]

    except (json.JSONDecodeError, TypeError):
        return None


def _strip_json_fence(content: Optional[str]) -> Optional[str]:
    if content is None:
        return None
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    return content


def _trim_word_enrichment(entry) -> Optional[dict]:
    if not isinstance(entry, dict):
        return None

    usage_note = str(entry.get("usage_note") or "").strip()
    contexts = []
    for item in entry.get("context_meanings") or []:
        if not isinstance(item, dict):
            continue
        context = str(item.get("context") or "").strip()
        meaning = str(item.get("meaning") or "").strip()
        example = str(item.get("example") or "").strip()
        if not context or not meaning:
            continue
        normalized = {"context": context[:40], "meaning": meaning[:80]}
        if example:
            normalized["example"] = example[:120]
        contexts.append(normalized)
        if len(contexts) >= 2:
            break

    if not usage_note and not contexts:
        return None
    return {
        "usage_note": usage_note[:80] if usage_note else None,
        "context_meanings": contexts,
    }


def _parse_word_enrichments(content: Optional[str], words: list[str]) -> dict[str, dict]:
    content = _strip_json_fence(content)
    if content is None:
        return {}
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}

    allowed = {word.strip().lower(): word for word in words if word}
    results = {}
    for raw_word, entry in parsed.items():
        key = str(raw_word or "").strip().lower()
        canonical = allowed.get(key)
        if not canonical:
            continue
        normalized = _trim_word_enrichment(entry)
        if normalized:
            results[canonical] = normalized
    return results


async def generate_distractors(phrase: str, meaning: str, count: int = 3) -> Optional[list[str]]:
    """Generate near-synonym distractors for a phrase meaning using DeepSeek."""
    content = await _call_deepseek(
        _SYSTEM_PROMPT,
        _USER_TEMPLATE.format(phrase=phrase, meaning=meaning),
    )
    raw = _parse_json_array(content, count)
    if raw is None:
        return None
    return [d for d in raw if d != meaning.strip()][:count]


async def generate_phrase_distractors(phrase: str, meaning: str, count: int = 3) -> Optional[list[str]]:
    """Generate similar English phrase distractors for meaning-to-phrase questions."""
    content = await _call_deepseek(
        _PHRASE_SYSTEM_PROMPT,
        _PHRASE_USER_TEMPLATE.format(phrase=phrase, meaning=meaning),
    )
    raw = _parse_json_array(content, count)
    if raw is None:
        return None
    return [d for d in raw if d.lower() != phrase.strip().lower()][:count]


async def generate_hard_distractors(
    *,
    question_type: str,
    correct: str,
    target_language: str = "auto",
    prompt: str = "",
    item_text: str = "",
    meaning: str = "",
    part_of_speech: str = "",
    example: str = "",
    candidates: list[str] = None,
    count: int = 3,
) -> Optional[list[str]]:
    """Generate moderately challenging distractors for learn and quiz flows."""
    content = await _call_deepseek(
        _HARD_DISTRACTOR_SYSTEM_PROMPT,
        _HARD_DISTRACTOR_USER_TEMPLATE.format(
            question_type=question_type,
            target_language=target_language,
            prompt=prompt,
            item_text=item_text,
            correct=correct,
            meaning=meaning,
            part_of_speech=part_of_speech,
            example=example,
            candidates_json=json.dumps((candidates or [])[:20], ensure_ascii=False),
        ),
        max_tokens=220,
        read_timeout=12.0,
    )
    return _parse_json_array(content, count)


async def generate_word_enrichments(words: list[dict]) -> dict[str, dict]:
    """Generate compact usage/context notes for a batch of words."""
    if not words:
        return {}

    payload = []
    word_names = []
    for word in words[:20]:
        name = str(word.get("word") or "").strip()
        if not name:
            continue
        word_names.append(name)
        payload.append({
            "word": name,
            "part_of_speech": word.get("part_of_speech") or "",
            "meaning": word.get("meaning") or "",
            "example": word.get("example") or "",
        })

    if not payload:
        return {}

    content = await _call_deepseek(
        _WORD_ENRICHMENT_SYSTEM_PROMPT,
        _WORD_ENRICHMENT_USER_TEMPLATE.format(
            words_json=json.dumps(payload, ensure_ascii=False)
        ),
        max_tokens=3200,
        read_timeout=30.0,
    )
    return _parse_word_enrichments(content, word_names)
