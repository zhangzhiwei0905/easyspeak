"""DeepSeek AI client for generating quiz distractors."""

import json
import logging
import httpx
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

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


async def generate_distractors(phrase: str, meaning: str, count: int = 3) -> Optional[list[str]]:
    """Generate near-synonym distractors for a phrase meaning using DeepSeek.

    Returns None if the API call fails (caller should fall back to random distractors).
    """
    settings = get_settings()
    api_key = getattr(settings, "DEEPSEEK_API_KEY", "")
    api_url = getattr(settings, "DEEPSEEK_API_URL", "https://api.deepseek.com/v1")

    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": _USER_TEMPLATE.format(phrase=phrase, meaning=meaning)},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 100,
                },
            )

            if response.status_code != 200:
                logger.warning("DeepSeek API returned status %d: %s", response.status_code, response.text[:200])
                return None

            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Parse JSON array from response (handle markdown code blocks)
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            distractors = json.loads(content)

            if not isinstance(distractors, list) or len(distractors) < count:
                return None

            # Filter: remove any that match the correct answer
            result = [d.strip() for d in distractors if d.strip() and d.strip() != meaning.strip()]
            return result[:count]

    except (httpx.TimeoutException, httpx.ConnectError) as e:
        logger.warning("DeepSeek API connection error: %s", e)
        return None
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning("DeepSeek API response parse error: %s", e)
        return None
    except Exception as e:
        logger.warning("DeepSeek API unexpected error: %s", e)
        return None
