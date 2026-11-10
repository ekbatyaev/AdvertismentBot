import unittest

from app.ai.functions.ad_analysis import _normalize_answers, _parse_fine


class ParseFineTests(unittest.TestCase):
    def test_integer(self):
        self.assertEqual(_parse_fine(500000), 500000)

    def test_range_string_takes_maximum(self):
        self.assertEqual(_parse_fine("100 000 - 500 000 \u20bd"), 500000)

    def test_range_with_words(self):
        self.assertEqual(_parse_fine("от 100 000 до 500 000 руб."), 500000)

    def test_none(self):
        self.assertEqual(_parse_fine(None), 0)

    def test_bool_is_not_number(self):
        self.assertEqual(_parse_fine(True), 0)

    def test_negative_becomes_zero(self):
        self.assertEqual(_parse_fine(-100), 0)


class NormalizeAnswersTests(unittest.TestCase):
    def test_string_fine_is_parsed(self):
        answers = _normalize_answers(
            {
                "analysis": [
                    {
                        "violations": "\u0414\u0430",
                        "description": "desc",
                        "fine": "\u043e\u0442 100 000 \u0434\u043e 500 000",
                        "recommendation": "rec",
                    }
                ]
            }
        )
        self.assertEqual(answers[0]["fine"], 500000)
        self.assertEqual(answers[0]["violations"], "\u0414\u0430")


if __name__ == "__main__":
    unittest.main()
