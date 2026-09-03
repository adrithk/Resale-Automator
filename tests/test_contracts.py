"""Tests for the Phase III structured data contract."""

import unittest

from contracts import (
    ClothingFact,
    EvidenceClaim,
    PipelineResult,
    ValidatedClothingFacts,
)


class ClothingFactTests(unittest.TestCase):
    def test_known_fact_serializes_confidence_and_provenance(self) -> None:
        fact = ClothingFact(
            value="Levi's",
            confidence=0.98,
            provenance=("tag_photo",),
        )

        self.assertEqual(
            fact.to_dict(),
            {
                "value": "Levi's",
                "confidence": 0.98,
                "provenance": ["tag_photo"],
                "needs_review": False,
            },
        )

    def test_unknown_fact_uses_null_instead_of_placeholder_text(self) -> None:
        self.assertEqual(
            ClothingFact.unknown().to_dict(),
            {
                "value": None,
                "confidence": 0,
                "provenance": [],
                "needs_review": False,
            },
        )

    def test_confidence_must_be_between_zero_and_one(self) -> None:
        with self.assertRaisesRegex(ValueError, "confidence"):
            ClothingFact(value="blue", confidence=1.01, provenance=("item_photo_1",))

    def test_known_fact_requires_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "provenance"):
            ClothingFact(value="blue", confidence=0.8)

    def test_conflicting_evidence_requires_review(self) -> None:
        conflict = EvidenceClaim(
            value="navy",
            confidence=0.7,
            provenance=("item_photo_2",),
        )

        with self.assertRaisesRegex(ValueError, "conflicting evidence"):
            ClothingFact(
                value="black",
                confidence=0.8,
                provenance=("item_photo_1",),
                conflicts=(conflict,),
            )


class ValidatedClothingFactsTests(unittest.TestCase):
    def test_brand_and_size_require_tag_or_user_correction(self) -> None:
        invalid_brand = ClothingFact(
            value="Levi's",
            confidence=0.8,
            provenance=("item_photo_1",),
        )

        with self.assertRaisesRegex(ValueError, "brand"):
            ValidatedClothingFacts(brand=invalid_brand)

        corrected_size = ClothingFact(
            value="M",
            confidence=1,
            provenance=("user_correction",),
        )
        facts = ValidatedClothingFacts(size=corrected_size)
        self.assertEqual(facts.to_dict()["size"]["value"], "M")

    def test_brand_conflicts_follow_the_same_provenance_rule(self) -> None:
        fact = ClothingFact(
            value="Levi's",
            confidence=0.8,
            provenance=("tag_photo",),
            needs_review=True,
            conflicts=(
                EvidenceClaim(
                    value="Lee",
                    confidence=0.6,
                    provenance=("item_photo_1",),
                ),
            ),
        )

        with self.assertRaisesRegex(ValueError, "brand"):
            ValidatedClothingFacts(brand=fact)

    def test_condition_rejects_tag_only_evidence(self) -> None:
        tag_condition = ClothingFact(
            value="Good",
            confidence=0.9,
            provenance=("tag_photo",),
        )

        with self.assertRaisesRegex(ValueError, "condition"):
            ValidatedClothingFacts(condition=tag_condition)

    def test_candidate_fields_serialize_without_allowed_value_vocabularies(self) -> None:
        facts = ValidatedClothingFacts(
            category=ClothingFact(
                value="User-defined category",
                confidence=0.7,
                provenance=("item_photo_1",),
                needs_review=True,
            ),
            age=ClothingFact.unknown(needs_review=True),
        )
        serialized = facts.to_dict()

        self.assertEqual(serialized["category"]["value"], "User-defined category")
        self.assertIsNone(serialized["brand"])
        self.assertIsNone(serialized["age"]["value"])

    def test_source_fields_are_part_of_the_fact_contract(self) -> None:
        facts = ValidatedClothingFacts(
            source_1=ClothingFact(
                value="Preloved (preloved)",
                confidence=0.9,
                provenance=("item_photo_1",),
            ),
            source_2=ClothingFact.unknown(needs_review=True),
        ).to_dict()

        self.assertEqual(facts["source_1"]["value"], "Preloved (preloved)")
        self.assertIsNone(facts["source_2"]["value"])

    def test_pipeline_result_keeps_stages_separate(self) -> None:
        result = PipelineResult(
            status="quality_checks_complete",
            image_analysis={"item_photos": [], "tag_photo": {}},
        ).to_dict()

        self.assertEqual(result["image_analysis"]["item_photos"], [])
        self.assertIsNone(result["model_analysis"])
        self.assertIsNone(result["validated_facts"])
        self.assertIsNone(result["listing_draft"])


if __name__ == "__main__":
    unittest.main()
