"""Offline tests for deterministic Depop CSV export."""

import csv
import json
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from depop_csv import DEPOP_CSV_COLUMNS, DepopCsvError, generate_depop_csv
from review_validation import FINAL_FACT_NAMES

PICTURE_URLS = [f"https://res.cloudinary.com/test-cloud/image/upload/v1/relist/{index:064x}.jpg" for index in range(3)]

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
        }
    )
    values.update(overrides)
    return values


class DepopCsvTests(unittest.TestCase):
    def setUp(self):
        location_patch = patch.dict("os.environ", {"DEPOP_SHIPPING_LOCATION": "California, United States"})
        location_patch.start()
        self.addCleanup(location_patch.stop)

    def test_exports_exact_columns_and_one_approved_row(self) -> None:
        contents = generate_depop_csv(
            approved_facts(),
            {"draft_title": "Levi's Black Jeans", "description": "Approved description."},
            price="12",
            picture_urls=PICTURE_URLS,
        )
        raw_rows = list(csv.reader(StringIO(contents)))
        reference = json.loads(
            (Path(__file__).parent / "fixtures" / "depop_csv_template_v6.json").read_text()
        )
        self.assertEqual(raw_rows[:3], reference["rows"])
        self.assertEqual(len(raw_rows), 4)
        self.assertTrue(all(len(row) == 26 for row in raw_rows))
        rows = [dict(zip(raw_rows[1], raw_rows[3]))]

        self.assertEqual(tuple(raw_rows[1]), DEPOP_CSV_COLUMNS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Description"], "Approved description.")
        self.assertEqual(rows[0]["Brand"], "Levi's (levi-s)")
        self.assertEqual(rows[0]["Size"], '36"')
        self.assertEqual(rows[0]["Color 1"], "Black (black)")
        self.assertEqual(rows[0]["Price"], "12.00")
        self.assertEqual(rows[0]["Location"], "California, United States")
        self.assertEqual(rows[0]["Picture Hero url"], PICTURE_URLS[0])
        self.assertEqual(raw_rows[3][15:18], PICTURE_URLS)
        self.assertEqual(raw_rows[3][18:23], [""] * 5)
        self.assertNotIn("draft_title", rows[0])
        self.assertNotIn("Inseam", rows[0])

    def test_round_trips_quotes_commas_newlines_and_unicode(self) -> None:
        description = 'Levi’s jeans, waist 36".\nBlue & cream — café.'
        rows = list(csv.reader(StringIO(generate_depop_csv(
            approved_facts(), {"draft_title": "Jeans", "description": description}, price="12.50", picture_urls=PICTURE_URLS
        ))))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[3][0], description)
        self.assertEqual(rows[3][1], approved_facts()["category"])

    def test_template_description_limits_are_enforced_at_export(self) -> None:
        for description in ["a" * 1001, "#one #two #three #four #five #six"]:
            with self.subTest(description=description):
                with self.assertRaisesRegex(DepopCsvError, "description"):
                    generate_depop_csv(
                        approved_facts(), {"draft_title": "Jeans", "description": description}, price="12"
                    )
        for description in ["a" * 1000, "#one #two #three #four #five"]:
            self.assertTrue(generate_depop_csv(
                approved_facts(), {"draft_title": "Jeans", "description": description}, price="12", picture_urls=PICTURE_URLS
            ))

    def test_rejects_invalid_data_before_export(self) -> None:
        with self.assertRaisesRegex(DepopCsvError, "size"):
            generate_depop_csv(
                approved_facts(size="banana"),
                {"draft_title": "Title", "description": "Description"},
                price="12",
            )

    def test_missing_price_and_invalid_location_cannot_produce_csv(self):
        draft = {"draft_title": "Title", "description": "Description"}
        for value in [None, "", "0", "NaN", "$12"]:
            with self.subTest(value=value), self.assertRaises(DepopCsvError):
                generate_depop_csv(approved_facts(), draft, price=value)
        with patch.dict("os.environ", {"DEPOP_SHIPPING_LOCATION": "private-test-address"}):
            with self.assertRaises(DepopCsvError) as caught:
                generate_depop_csv(approved_facts(), draft, price="12")
            self.assertNotIn("private-test-address", str(caught.exception))

    def test_configured_dropdown_location_is_used(self):
        with patch.dict("os.environ", {"DEPOP_SHIPPING_LOCATION": "United States"}):
            rows = list(csv.reader(StringIO(generate_depop_csv(
                approved_facts(), {"draft_title": "Title", "description": "Description"}, price="15", picture_urls=PICTURE_URLS
            ))))
        self.assertEqual(rows[3][14], "United States")

    def test_missing_invalid_or_excess_photos_block_export(self):
        for urls in ([], PICTURE_URLS[:2], PICTURE_URLS * 3, ["http://localhost/photo.jpg"] * 3):
            with self.subTest(urls=urls), self.assertRaises(DepopCsvError):
                generate_depop_csv(approved_facts(), {"draft_title": "Title", "description": "Description"}, price="12", picture_urls=urls)

    def test_all_eight_photo_columns_are_filled(self):
        urls = [f"https://res.cloudinary.com/test-cloud/image/upload/v1/relist/{index:064x}.jpg" for index in range(8)]
        contents = generate_depop_csv(approved_facts(), {"draft_title": "Title", "description": "Description"}, price="12", picture_urls=urls)
        self.assertEqual(list(csv.reader(StringIO(contents)))[3][15:23], urls)


if __name__ == "__main__":
    unittest.main()
