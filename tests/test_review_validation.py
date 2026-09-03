"""Offline tests for final user-edit validation."""

import unittest

from review_validation import FINAL_FACT_NAMES, validate_final_edits


def valid_edits(**overrides):
    values = {name: None for name in FINAL_FACT_NAMES}
    values.update(
        {
            "category": "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)",
            "item_type": "Jeans",
            "brand": "Levi's",
            "condition": "Used - Good",
            "size": '36"',
            "inseam": "34",
            "primary_color": "Black",
            "source_1": "Preloved",
            "style_1": "Casual",
        }
    )
    values.update(overrides)
    return values


class FinalEditValidationTests(unittest.TestCase):
    def test_valid_edits_are_canonicalized_without_provenance(self) -> None:
        outcome = validate_final_edits(valid_edits())

        self.assertTrue(outcome.is_valid)
        self.assertEqual(outcome.approved_facts["brand"], "Levi's (levi-s)")
        self.assertEqual(outcome.approved_facts["size"], '36"')
        self.assertEqual(outcome.approved_facts["inseam"], '34"')
        self.assertNotIn("provenance", outcome.approved_facts)

    def test_plain_numeric_jeans_size_becomes_waist_inches(self) -> None:
        outcome = validate_final_edits(valid_edits(size="32"))

        self.assertTrue(outcome.is_valid)
        self.assertEqual(outcome.approved_facts["size"], '32"')

    def test_arbitrary_size_text_is_rejected(self) -> None:
        outcome = validate_final_edits(valid_edits(size="banana"))

        self.assertFalse(outcome.is_valid)
        self.assertIn(
            ("size", "unsupported_size"),
            {(error["field"], error["code"]) for error in outcome.errors},
        )

    def test_size_must_belong_to_selected_category(self) -> None:
        outcome = validate_final_edits(
            valid_edits(
                category="Women >> Dresses >> Going out dresses",
                size='36"',
            )
        )

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.errors[-1]["code"], "unsupported_size")

    def test_invalid_dropdown_and_brand_values_are_rejected(self) -> None:
        outcome = validate_final_edits(
            valid_edits(brand="Made Up Brand", condition="pretty good")
        )

        invalid_fields = {
            error["field"] for error in outcome.errors if error["code"] == "unsupported_value"
        }
        self.assertEqual(invalid_fields, {"brand", "condition"})

    def test_optional_values_can_be_blank(self) -> None:
        outcome = validate_final_edits(
            valid_edits(
                secondary_color="",
                source_2=None,
                age="",
                style_2="",
                style_3=None,
            )
        )

        self.assertTrue(outcome.is_valid)
        self.assertIsNone(outcome.approved_facts["age"])

    def test_required_values_and_inseam_format_are_checked(self) -> None:
        outcome = validate_final_edits(valid_edits(category="", inseam="thirty four"))
        errors = {(error["field"], error["code"]) for error in outcome.errors}

        self.assertIn(("category", "required_value"), errors)
        self.assertIn(("inseam", "invalid_measurement"), errors)


if __name__ == "__main__":
    unittest.main()
