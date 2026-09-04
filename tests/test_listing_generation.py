"""Offline tests for deterministic listing-draft generation."""

import unittest

from listing_generation import (
    ListingGenerationError,
    generate_listing_draft,
    validate_listing_draft,
)
from review_validation import FINAL_FACT_NAMES


def approved_facts(**overrides):
    values = {name: None for name in FINAL_FACT_NAMES}
    values.update(
        {
            "category": "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)",
            "item_type": "Jeans",
            "brand": "Levi's (levi-s)",
            "condition": "Used - Good (used_good)",
            "size": '36"',
            "inseam": '34"',
            "primary_color": "Black (black)",
            "source_1": "Preloved (preloved)",
            "style_1": "Casual (casual)",
            "style_2": "Streetwear (streetwear)",
        }
    )
    values.update(overrides)
    return values


class ListingGenerationTests(unittest.TestCase):
    def test_generates_title_and_description_from_approved_facts(self) -> None:
        draft = generate_listing_draft(approved_facts()).to_dict()

        self.assertEqual(draft["draft_title"], "Levi's Black Jeans")
        self.assertIn('34" inseam', draft["description"])
        self.assertIn('Size: 36"', draft["description"])
        self.assertNotIn("waist", draft["description"])
        self.assertEqual(draft["description"], 'Levi\'s Black Jeans. Size: 36" with a 34" inseam.')
        self.assertNotIn("(levi-s)", draft["description"])

    def test_letter_size_uses_neutral_size_label(self) -> None:
        draft = generate_listing_draft(approved_facts(
            category="Men >> Coats and jackets >> Vests (menswear, coats-jackets, gilets)",
            item_type="Sweater vest", size="M", inseam=None,
        ))
        self.assertIn("Size: M.", draft.description)
        self.assertNotIn("waist", draft.description)
        self.assertEqual(draft.description, "Levi's Black Sweater vest. Size: M.")

    def test_optional_attributes_do_not_add_description_prose(self) -> None:
        facts = approved_facts(secondary_color="Blue (blue)", age="Modern (modern)")
        draft = generate_listing_draft(facts)
        self.assertEqual(draft.description, 'Levi\'s Black Jeans. Size: 36" with a 34" inseam.')
        self.assertEqual(facts["style_1"], "Casual (casual)")
        self.assertEqual(facts["condition"], "Used - Good (used_good)")

    def test_omits_blank_optional_facts(self) -> None:
        draft = generate_listing_draft(
            approved_facts(inseam=None, style_1=None, style_2=None, age=None)
        ).to_dict()

        self.assertNotIn("inseam", draft["description"])
        self.assertNotIn("Style:", draft["description"])
        self.assertNotIn("Age:", draft["description"])

    def test_rejects_invalid_facts_before_generating_text(self) -> None:
        with self.assertRaisesRegex(ListingGenerationError, "size"):
            generate_listing_draft(approved_facts(size="banana"))

    def test_final_draft_requires_non_empty_title_and_description(self) -> None:
        draft, errors = validate_listing_draft(
            {"draft_title": "", "description": "Description"}
        )

        self.assertIsNone(draft)
        self.assertEqual(errors[0]["field"], "draft_title")


if __name__ == "__main__":
    unittest.main()
