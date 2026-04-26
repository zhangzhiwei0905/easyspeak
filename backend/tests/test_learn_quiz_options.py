import unittest
from unittest.mock import patch

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.phrase import Phrase
from app.models.word import Word
from app.routers.learn import _phrase_stage2_quiz, _word_stage2_quiz


class LearnQuizOptionsTest(unittest.TestCase):
    def test_phrase_english_to_chinese_quiz_uses_chinese_options_only(self):
        phrase = Phrase(id=1, content_id=1, phrase="grab a bite", meaning="吃点东西", explanation="快速吃一点东西。")

        with patch("app.routers.learn.random.shuffle", lambda items: None):
            quiz = _phrase_stage2_quiz(
                phrase,
                0,
                "吃点东西",
                ["go out", "take a break", "搭帐篷", "我请客"],
                ["grab a bite", "go out", "take a break"],
                [],
            )

        option_texts = [option.text for option in quiz.options]
        self.assertEqual(quiz.question, "grab a bite 是什么意思？")
        self.assertEqual(len(option_texts), 4)
        self.assertTrue(all(self._contains_cjk(text) for text in option_texts))
        self.assertNotIn("go out", option_texts)
        self.assertNotIn("take a break", option_texts)

    def test_word_english_to_chinese_quiz_uses_chinese_options_only(self):
        word = Word(id=1, content_id=1, word="latte", meaning="拿铁", phonetic="/latte/")

        with patch("app.routers.learn.random.shuffle", lambda items: None):
            quiz = _word_stage2_quiz(
                word,
                0,
                ["espresso", "cappuccino", "浓缩咖啡", "摩卡"],
                ["latte", "espresso", "cappuccino"],
                [],
            )

        option_texts = [option.text for option in quiz.options]
        self.assertEqual(quiz.question, "latte 是什么意思？")
        self.assertEqual(len(option_texts), 4)
        self.assertTrue(all(self._contains_cjk(text) for text in option_texts))
        self.assertNotIn("espresso", option_texts)
        self.assertNotIn("cappuccino", option_texts)

    @staticmethod
    def _contains_cjk(text):
        return any("\u3400" <= char <= "\u9fff" for char in text)


if __name__ == "__main__":
    unittest.main()
