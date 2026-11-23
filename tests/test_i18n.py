"""Regression tests for the Japanese/English translation dictionary."""

import unittest

from focusloop.i18n import ENGLISH, LANGUAGES, phase_name, translate


class TranslationTests(unittest.TestCase):
    def test_english_translates_core_controls_and_palette(self):
        self.assertEqual(LANGUAGES, ("ja", "en"))
        for key in ("設定", "言語", "一時停止", "再開", "閉じる", "設定初期化",
                    "非表示", "フェーズ名", "削除", "中央", "アンバー", "ローズ"):
            with self.subTest(key=key):
                self.assertNotEqual(translate(key, "en"), key)
                self.assertEqual(translate(key, "ja"), key)
        self.assertEqual(translate("Simple", "en"), "Simple")
        self.assertEqual(translate("custom value", "en"), "custom value")

    def test_built_in_names_are_display_only_and_round_trip(self):
        built_ins = ("作業中", "休憩中", "作業", "休憩", "新しいフェーズ")
        for name in built_ins:
            with self.subTest(name=name):
                translated = phase_name(name, "en")
                self.assertNotEqual(translated, name)
                self.assertEqual(phase_name(translated, "ja"), name)
        for custom in ("My focus", "集中", "休憩を長めに", "Deep work"):
            self.assertEqual(phase_name(custom, "en"), custom)
            self.assertEqual(phase_name(custom, "ja"), custom)

    def test_no_empty_english_text(self):
        self.assertTrue(ENGLISH)
        self.assertTrue(all(isinstance(value, str) and value.strip()
                            for value in ENGLISH.values()))


if __name__ == "__main__":
    unittest.main()
