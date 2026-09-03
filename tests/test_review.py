"""Offline tests for interactive terminal review."""

import io
import unittest

from review import (
    ReviewCancelled,
    review_facts_interactively,
    review_listing_draft_interactively,
)
from review_validation import FINAL_FACT_NAMES


def initial_facts():
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
        }
    )
    return {name: {"value": value} for name, value in values.items()}


class InteractiveReviewTests(unittest.TestCase):
    def test_enter_keeps_values_dash_clears_and_yes_approves(self) -> None:
        responses = iter(
            [
                "", "", "", "", "", "", "", "", "", "", "", "", "", "", "yes"
            ]
        )
        approved = review_facts_interactively(
            initial_facts(),
            input_fn=lambda prompt: next(responses),
            output=io.StringIO(),
        )

        self.assertEqual(approved["size"], '36"')
        self.assertIsNone(approved["age"])

    def test_invalid_size_is_reprompted_before_approval(self) -> None:
        first_pass = [""] * len(FINAL_FACT_NAMES)
        first_pass[FINAL_FACT_NAMES.index("size")] = "banana"
        responses = iter([*first_pass, '36"', "y"])
        output = io.StringIO()

        approved = review_facts_interactively(
            initial_facts(),
            input_fn=lambda prompt: next(responses),
            output=output,
        )

        self.assertEqual(approved["size"], '36"')
        self.assertIn("exact size", output.getvalue())

    def test_plain_numeric_jeans_size_is_accepted_without_reprompting(self) -> None:
        first_pass = [""] * len(FINAL_FACT_NAMES)
        first_pass[FINAL_FACT_NAMES.index("size")] = "32"
        responses = iter([*first_pass, "y"])

        approved = review_facts_interactively(
            initial_facts(),
            input_fn=lambda prompt: next(responses),
            output=io.StringIO(),
        )

        self.assertEqual(approved["size"], '32"')

    def test_q_cancels_without_approval(self) -> None:
        with self.assertRaises(ReviewCancelled):
            review_facts_interactively(
                initial_facts(),
                input_fn=lambda prompt: "q",
                output=io.StringIO(),
            )

    def test_listing_text_can_be_edited_and_approved(self) -> None:
        responses = iter(["Updated title", "", "yes"])
        draft = review_listing_draft_interactively(
            {"draft_title": "Original title", "description": "Original description"},
            input_fn=lambda prompt: next(responses),
            output=io.StringIO(),
        )

        self.assertEqual(draft["draft_title"], "Updated title")
        self.assertEqual(draft["description"], "Original description")


if __name__ == "__main__":
    unittest.main()
