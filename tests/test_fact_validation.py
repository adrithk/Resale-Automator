"""Tests for candidate conversion, provenance, tag gating, and mapping."""

import unittest

from fact_validation import validate_candidate_analysis
from openai_vision import FACT_NAMES


def candidate_fact(value=None, *, confidence=0, provenance=(), evidence=None, needs_review=False, conflicts=()):
    return {
        "value": value,
        "confidence": confidence,
        "provenance": list(provenance),
        "needs_review": needs_review,
        "evidence": evidence,
        "conflicts": list(conflicts),
    }


def analysis_with(status="readable", **facts):
    candidates = {name: candidate_fact() for name in FACT_NAMES}
    candidates.update(facts)
    return {
        "schema_version": 1,
        "tag_readability": {
            "status": status,
            "confidence": 0.9,
            "issues": [],
            "retake_instructions": (
                [] if status == "readable" else ["Retake the full tag in even light."]
            ),
        },
        "facts": candidates,
        "warnings": [],
    }


def known(value, provenance, confidence=0.9, **overrides):
    return candidate_fact(
        value,
        confidence=confidence,
        provenance=provenance,
        evidence=f"Visible evidence for {value}",
        **overrides,
    )


class TagGateTests(unittest.TestCase):
    def test_unreadable_tag_stops_before_validated_facts(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                "unreadable",
                brand=known("Levi's", ("tag_photo",)),
            )
        )

        self.assertIsNone(outcome.validated_facts)
        self.assertEqual(outcome.issues[0]["code"], "tag_not_readable")
        self.assertIn("even light", outcome.tag_retake_instructions[0])

    def test_uncertain_tag_stops_and_supplies_fallback_retake_help(self) -> None:
        analysis = analysis_with("uncertain")
        analysis["tag_readability"]["retake_instructions"] = []

        outcome = validate_candidate_analysis(analysis)

        self.assertIsNone(outcome.validated_facts)
        self.assertTrue(outcome.tag_retake_instructions)
        self.assertIn("focus", outcome.tag_retake_instructions[0])


class FactMappingTests(unittest.TestCase):
    def test_levi_strauss_tag_label_maps_without_weakening_provenance(self):
        for label in ("LEVI STRAUSS & CO.", "Levi Strauss and Co."):
            with self.subTest(label=label):
                outcome = validate_candidate_analysis(analysis_with(
                    brand=known(label, ("tag_photo",)),
                ))
                self.assertEqual(outcome.validated_facts.to_dict()["brand"]["value"], "Levi's (levi-s)")
        outcome = validate_candidate_analysis(analysis_with(
            brand=known("Levi Strauss & Co.", ("item_photo_1",)),
        ))
        self.assertIsNone(outcome.validated_facts.to_dict()["brand"]["value"])

    def test_exact_mapping_and_category_dependent_size(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                category=known(
                    "Women >> Dresses >> Going out dresses (womenswear, dresses, going-out-dresses)",
                    ("item_photo_1",),
                ),
                brand=known("Levi's", ("tag_photo",)),
                condition=known("used_good", ("item_photo_2",)),
                size=known("medium", ("tag_photo",)),
                primary_color=known("gray", ("item_photo_1",)),
                source_1=known("Preloved", ("item_photo_1",)),
            )
        )
        facts = outcome.validated_facts.to_dict()

        self.assertEqual(
            facts["category"]["value"],
            "Women >> Dresses >> Going out dresses (womenswear, dresses, going-out-dresses)",
        )
        self.assertEqual(facts["size"]["value"], "M")
        self.assertEqual(facts["brand"]["value"], "Levi's (levi-s)")
        self.assertEqual(facts["condition"]["value"], "Used - Good (used_good)")
        self.assertEqual(facts["primary_color"]["value"], "Grey (grey)")
        self.assertEqual(facts["source_1"]["value"], "Preloved (preloved)")

    def test_jeans_size_uses_waist_and_retains_tag_inseam(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                category=known(
                    "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)",
                    ("item_photo_1",),
                ),
                size=known("W36 L34", ("tag_photo",)),
            )
        )
        facts = outcome.validated_facts.to_dict()

        self.assertEqual(facts["size"]["value"], '36"')
        self.assertEqual(facts["inseam"]["value"], '34"')
        self.assertEqual(facts["inseam"]["provenance"], ["tag_photo"])
        self.assertNotIn(
            ("size", "unmapped_value"),
            {(issue["field"], issue["code"]) for issue in outcome.issues},
        )

    def test_jeans_waist_by_length_tag_formats_retain_both_measurements(self) -> None:
        for labeled_size in (
            "32×34inch",
            "32x34",
            "32 X 34 inches",
            "Waist×Length 32×34inch",
            "Waist x Inseam 32 x 34 in.",
        ):
            with self.subTest(labeled_size=labeled_size):
                outcome = validate_candidate_analysis(
                    analysis_with(
                        category=known(
                            "Men >> Bottoms >> Jeans (menswear, bottoms, jeans)",
                            ("item_photo_1",),
                        ),
                        size=known(labeled_size, ("tag_photo",)),
                    )
                )
                facts = outcome.validated_facts.to_dict()

                self.assertEqual(facts["size"]["value"], '32"')
                self.assertEqual(facts["inseam"]["value"], '34"')
                self.assertNotIn(
                    ("size", "unmapped_value"),
                    {(issue["field"], issue["code"]) for issue in outcome.issues},
                )

    def test_review_flagged_age_is_left_blank(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                age=known(
                    "Modern (modern)",
                    ("item_photo_1",),
                    needs_review=True,
                )
            )
        )
        facts = outcome.validated_facts.to_dict()

        self.assertIsNone(facts["age"]["value"])
        self.assertIn(
            ("age", "age_requires_confirmation"),
            {(issue["field"], issue["code"]) for issue in outcome.issues},
        )

    def test_review_flagged_exact_style_is_accepted_without_conflict(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                style_2=known(
                    "Streetwear (streetwear)",
                    ("item_photo_1",),
                    confidence=0.62,
                    needs_review=True,
                )
            )
        )
        fact = outcome.validated_facts.to_dict()["style_2"]

        self.assertEqual(fact["value"], "Streetwear (streetwear)")
        self.assertFalse(fact["needs_review"])

    def test_source_values_must_match_confirmed_vocabulary(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                source_1=known("Bought somewhere", ("item_photo_1",)),
                source_2=known("Designer", ("tag_photo",)),
            )
        )
        facts = outcome.validated_facts.to_dict()

        self.assertIsNone(facts["source_1"]["value"])
        self.assertEqual(facts["source_2"]["value"], "Designer (designer)")
        self.assertIn(
            "source_1",
            {issue["field"] for issue in outcome.issues if issue["code"] == "unmapped_value"},
        )

    def test_unmapped_category_prevents_size_mapping(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                category=known("Probably some dress", ("item_photo_1",)),
                size=known("M", ("tag_photo",)),
            )
        )
        facts = outcome.validated_facts.to_dict()

        self.assertIsNone(facts["category"]["value"])
        self.assertIsNone(facts["size"]["value"])
        issue_codes = {(issue["field"], issue["code"]) for issue in outcome.issues}
        self.assertIn(("category", "unmapped_value"), issue_codes)
        self.assertIn(("size", "size_requires_category"), issue_codes)

    def test_unknown_values_remain_null_and_require_review(self) -> None:
        outcome = validate_candidate_analysis(analysis_with())
        facts = outcome.validated_facts.to_dict()

        self.assertIsNone(facts["brand"]["value"])
        self.assertEqual(facts["brand"]["confidence"], 0)
        self.assertTrue(facts["brand"]["needs_review"])
        self.assertTrue(outcome.needs_review)

    def test_invalid_brand_and_condition_provenance_are_not_validated(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                brand=known("Levi's", ("item_photo_1",)),
                condition=known("Used - Good", ("tag_photo",)),
            )
        )
        facts = outcome.validated_facts.to_dict()

        self.assertIsNone(facts["brand"]["value"])
        self.assertIsNone(facts["condition"]["value"])
        invalid_fields = {
            issue["field"] for issue in outcome.issues if issue["code"] == "invalid_candidate"
        }
        self.assertEqual(invalid_fields, {"brand", "condition"})

    def test_visible_fields_reject_tag_provenance(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                primary_color=known("Black", ("tag_photo",)),
                style_1=known("Utility (techwear)", ("tag_photo",)),
            )
        )
        facts = outcome.validated_facts.to_dict()

        self.assertIsNone(facts["primary_color"]["value"])
        self.assertIsNone(facts["style_1"]["value"])

    def test_placeholder_and_unsupported_style_become_unknown(self) -> None:
        placeholder_conflict = {
            "value": "null",
            "confidence": 0.4,
            "provenance": ["item_photo_1"],
        }
        outcome = validate_candidate_analysis(
            analysis_with(
                source_1=known("null", ("item_photo_1",)),
                style_1=known("five-pocket", ("item_photo_1",)),
                style_2=known("button fly", ("item_photo_1",)),
                primary_color=known("Black", ("item_photo_1",), conflicts=(placeholder_conflict,)),
            )
        )
        facts = outcome.validated_facts.to_dict()

        self.assertIsNone(facts["source_1"]["value"])
        self.assertIsNone(facts["style_1"]["value"])
        self.assertIsNone(facts["style_2"]["value"])
        self.assertIsNone(facts["primary_color"]["value"])
        invalid_fields = {issue["field"] for issue in outcome.issues if issue["code"] == "invalid_candidate"}
        self.assertIn("source_1", invalid_fields)
        self.assertIn("primary_color", invalid_fields)
        unmapped_fields = {issue["field"] for issue in outcome.issues if issue["code"] == "unmapped_value"}
        self.assertEqual({"style_1", "style_2"}, unmapped_fields & {"style_1", "style_2"})

    def test_conflicts_are_preserved_and_require_review(self) -> None:
        conflict = {
            "value": "Navy",
            "confidence": 0.7,
            "provenance": ["item_photo_2"],
        }
        outcome = validate_candidate_analysis(
            analysis_with(
                primary_color=known(
                    "Black",
                    ("item_photo_1",),
                    conflicts=(conflict,),
                )
            )
        )
        fact = outcome.validated_facts.to_dict()["primary_color"]

        self.assertEqual(fact["value"], "Black (black)")
        self.assertEqual(fact["conflicts"][0]["value"], "Navy (navy)")
        self.assertTrue(fact["needs_review"])

    def test_semantically_invalid_unknown_candidate_is_rejected(self) -> None:
        outcome = validate_candidate_analysis(
            analysis_with(
                brand=candidate_fact(None, confidence=0.8, provenance=("tag_photo",)),
            )
        )

        self.assertIsNone(outcome.validated_facts.to_dict()["brand"]["value"])
        self.assertIn(
            "brand",
            {issue["field"] for issue in outcome.issues if issue["code"] == "invalid_candidate"},
        )


if __name__ == "__main__":
    unittest.main()
