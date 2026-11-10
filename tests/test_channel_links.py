import unittest

from app.database.functions.channel_info import (
    channel_alias,
    chat_id_from_link,
    is_channel_link,
    normalize_channel_link,
)


class NormalizeChannelLinkTests(unittest.TestCase):
    def test_strips_trailing_slash(self):
        self.assertEqual(
            normalize_channel_link("https://max.ru/channel_systeme_electric/"),
            "https://max.ru/channel_systeme_electric",
        )

    def test_keeps_web_host_and_negative_id(self):
        self.assertEqual(
            normalize_channel_link("https://web.max.ru/-70937669495409"),
            "https://web.max.ru/-70937669495409",
        )

    def test_adds_scheme_and_lowercases_host(self):
        self.assertEqual(
            normalize_channel_link("  MAX.ru/Channel_Test  "),
            "https://max.ru/Channel_Test",
        )

    def test_empty(self):
        self.assertEqual(normalize_channel_link(""), "")


class ChannelAliasTests(unittest.TestCase):
    def test_alias_from_web_link(self):
        self.assertEqual(
            channel_alias("https://web.max.ru/-70937669495409/"),
            "-70937669495409",
        )


class ChatIdFromLinkTests(unittest.TestCase):
    def test_web_link_with_negative_id(self):
        self.assertEqual(
            chat_id_from_link("https://web.max.ru/-70937669495409"),
            -70937669495409,
        )

    def test_positive_id_becomes_negative(self):
        self.assertEqual(
            chat_id_from_link("https://max.ru/70937669495409"),
            -70937669495409,
        )

    def test_alias_has_no_chat_id(self):
        self.assertIsNone(
            chat_id_from_link("https://max.ru/channel_systeme_electric")
        )


class IsChannelLinkTests(unittest.TestCase):
    def test_accepts_max_hosts(self):
        self.assertTrue(is_channel_link("https://max.ru/channel_systeme_electric"))
        self.assertTrue(is_channel_link("https://web.max.ru/-70937669495409/"))

    def test_rejects_other_hosts_and_paths(self):
        self.assertFalse(is_channel_link("https://example.com/channel"))
        self.assertFalse(is_channel_link("https://max.ru/"))
        self.assertFalse(is_channel_link("https://max.ru/a/b"))
        self.assertFalse(is_channel_link(""))


if __name__ == "__main__":
    unittest.main()
