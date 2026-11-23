"""Regression tests for UI translation without changing phase names."""

import unittest

from focusloop.i18n import ENGLISH, LANGUAGES, translate


class TranslationTests(unittest.TestCase):
    def test_english_translates_core_controls_and_palette(self):
        self.assertEqual(LANGUAGES, ("ja", "en"))
        for key in ("設定", "言語", "一時停止", "再開", "閉じる", "設定初期化",
                    "非表示", "フェーズ名", "不透明度", "削除",
                    "中央", "アンバー", "ローズ"):
            with self.subTest(key=key):
                self.assertNotEqual(translate(key, "en"), key)
                self.assertEqual(translate(key, "ja"), key)
        self.assertEqual(translate("不透明度", "en"), "Opacity")
        self.assertEqual(translate("Simple", "en"), "Simple")
        self.assertEqual(translate("custom value", "en"), "custom value")

    def test_phase_names_are_not_part_of_the_translation_dictionary(self):
        for name in (
            "作業中", "休憩中", "作業", "休憩", "新しいフェーズ",
            "Working", "On Break", "New phase",
            "My focus", "集中", "深い集中", "Deep work",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, ENGLISH)
                self.assertEqual(translate(name, "ja"), name)
                self.assertEqual(translate(name, "en"), name)

    def test_no_empty_english_text(self):
        self.assertTrue(ENGLISH)
        self.assertTrue(all(isinstance(value, str) and value.strip()
                            for value in ENGLISH.values()))


if __name__ == "__main__":
    unittest.main()
