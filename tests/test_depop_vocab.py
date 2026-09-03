"""Tests for exact Depop template vocabulary mapping."""

import unittest

from depop_vocab import (
    DepopVocabulary,
    UnsupportedDepopFieldError,
    UnsupportedDepopValueError,
)


class DepopVocabularyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vocabulary = DepopVocabulary()

    def test_loads_version_six_complete_vocabularies(self) -> None:
        self.assertEqual(self.vocabulary.template_version, 6)
        self.assertEqual(len(self.vocabulary.values("category")), 319)
        self.assertEqual(len(self.vocabulary.values("brand")), 14_038)
        self.assertEqual(len(self.vocabulary.values("condition")), 5)
        self.assertEqual(len(self.vocabulary.values("color")), 19)
        self.assertEqual(len(self.vocabulary.values("source")), 8)
        self.assertEqual(len(self.vocabulary.values("age")), 8)
        self.assertEqual(len(self.vocabulary.values("style")), 32)
        self.assertEqual(len(self.vocabulary.values("location")), 664)

    def test_keeps_label_code_and_upload_value_separate(self) -> None:
        match = self.vocabulary.require_match("condition", "used_good")

        self.assertEqual(match.label, "Used - Good")
        self.assertEqual(match.code, "used_good")
        self.assertEqual(match.upload_value, "Used - Good (used_good)")

    def test_matches_labels_codes_and_explicit_aliases(self) -> None:
        self.assertEqual(
            self.vocabulary.require_match("primary_color", "gray").upload_value,
            "Grey (grey)",
        )
        self.assertEqual(
            self.vocabulary.require_match("style_1", "techwear").upload_value,
            "Utility (techwear)",
        )
        self.assertEqual(
            self.vocabulary.require_match("brand", "Levi's").upload_value,
            "Levi's (levi-s)",
        )

    def test_rejects_unsupported_values_instead_of_guessing(self) -> None:
        self.assertIsNone(self.vocabulary.match("color", "blue-green-ish"))

        with self.assertRaises(UnsupportedDepopValueError):
            self.vocabulary.require_match("color", "blue-green-ish")

    def test_size_options_depend_on_category(self) -> None:
        category = "Women >> Dresses >> Going out dresses"

        self.assertEqual(self.vocabulary.require_size(category, "medium"), "M")
        self.assertIn("10", self.vocabulary.valid_sizes(category))
        self.assertNotIn("US 10", self.vocabulary.valid_sizes(category))

        with self.assertRaises(UnsupportedDepopValueError):
            self.vocabulary.require_size(category, "US 10")

    def test_size_matching_preserves_inches(self) -> None:
        category = "Women >> Bottoms >> Leggings"

        self.assertEqual(self.vocabulary.require_size(category, '30"'), '30"')
        self.assertEqual(self.vocabulary.require_size(category, "30"), "30")

    def test_plain_numeric_jeans_size_is_normalized_to_waist_inches(self) -> None:
        mens_jeans = "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)"
        womens_jeans = "Women >> Bottoms >> Jeans (womenswear, bottoms, jeans)"

        self.assertEqual(self.vocabulary.match_size(mens_jeans, "32"), '32"')
        self.assertEqual(self.vocabulary.match_size(womens_jeans, "32"), '32"')

    def test_rejects_fields_without_a_dropdown_vocabulary(self) -> None:
        with self.assertRaises(UnsupportedDepopFieldError):
            self.vocabulary.values("price")


if __name__ == "__main__":
    unittest.main()
