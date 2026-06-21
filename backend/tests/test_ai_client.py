import os
import unittest
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite:////private/tmp/easyspeak-ai-client-test.db"

from app.utils import ai_client


class AiClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_word_enrichment_uses_larger_token_budget(self):
        with patch("app.utils.ai_client._call_deepseek", new=AsyncMock(return_value="{}")) as mocked:
            await ai_client.generate_word_enrichments([
                {
                    "word": "appointment",
                    "part_of_speech": "noun",
                    "meaning": "预约",
                    "example": "I have a 3 PM appointment.",
                }
            ])

        self.assertEqual(mocked.await_args.kwargs["max_tokens"], 3200)
        self.assertEqual(mocked.await_args.kwargs["read_timeout"], 30.0)

    async def test_distractor_generation_keeps_default_token_budget(self):
        with patch("app.utils.ai_client._call_deepseek", new=AsyncMock(return_value='["促成","阻碍","导致"]')) as mocked:
            await ai_client.generate_distractors("lead to", "导致")

        self.assertEqual(mocked.await_args.kwargs, {})


if __name__ == "__main__":
    unittest.main()
