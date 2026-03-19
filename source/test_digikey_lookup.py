"""Unit tests for digikey_lookup.py — pure logic functions only (no network)."""

import pytest
from digikey_lookup import (
    interpolate_price,
    find_variation,
    extract_fields,
    format_custom,
    parse_max,
    apply_max_limit,
    resolve_part_numbers,
)

# ---------------------------------------------------------------------------
# Sample data reused across tests
# ---------------------------------------------------------------------------

SAMPLE_PRICING = [
    {"BreakQuantity": 1, "UnitPrice": 0.96},
    {"BreakQuantity": 10, "UnitPrice": 0.67},
    {"BreakQuantity": 100, "UnitPrice": 0.494},
]

SAMPLE_PRODUCT = {
    "Product": {
        "Description": {
            "DetailedDescription": "Photodiode 880nm 20ns",
            "ProductDescription": "Photodiode",
        },
        "Manufacturer": {"Name": "ams-OSRAM"},
        "ManufacturerProductNumber": "BP 104 FAS-Z",
        "ProductUrl": "https://www.digikey.com/en/products/detail/test/12345",
        "ProductVariations": [
            {
                "DigiKeyProductNumber": "475-BP104FAS-ZTR-ND",
                "PackageType": {"Id": 1, "Name": "Tape & Reel (TR)"},
                "StandardPricing": [
                    {"BreakQuantity": 1500, "UnitPrice": 0.377},
                    {"BreakQuantity": 3000, "UnitPrice": 0.357},
                ],
                "MinimumOrderQuantity": 1500,
                "MarketPlace": False,
            },
            {
                "DigiKeyProductNumber": "475-BP104FAS-ZCT-ND",
                "PackageType": {"Id": 2, "Name": "Cut Tape (CT)"},
                "StandardPricing": [
                    {"BreakQuantity": 1, "UnitPrice": 0.96},
                    {"BreakQuantity": 10, "UnitPrice": 0.67},
                    {"BreakQuantity": 100, "UnitPrice": 0.494},
                ],
                "MinimumOrderQuantity": 1,
                "MarketPlace": False,
            },
            {
                "DigiKeyProductNumber": "475-BP104FAS-ZDKR-ND",
                "PackageType": {"Id": 3, "Name": "Digi-Reel"},
                "StandardPricing": [
                    {"BreakQuantity": 1, "UnitPrice": 0.96},
                ],
                "MinimumOrderQuantity": 1,
                "MarketPlace": False,
            },
        ],
    }
}


# ===========================================================================
# interpolate_price
# ===========================================================================

class TestInterpolatePrice:
    def test_exact_break(self):
        assert interpolate_price(SAMPLE_PRICING, 10) == 0.67

    def test_between_breaks(self):
        # qty 50 is above 10-break but below 100, so uses the 10-break price
        assert interpolate_price(SAMPLE_PRICING, 50) == 0.67

    def test_above_highest_break(self):
        assert interpolate_price(SAMPLE_PRICING, 1000) == 0.494

    def test_below_first_break(self):
        # qty 0 is below break 1, falls back to first break
        assert interpolate_price(SAMPLE_PRICING, 0) == 0.96

    def test_empty_pricing(self):
        assert interpolate_price([], 10) is None

    def test_single_break(self):
        pricing = [{"BreakQuantity": 100, "UnitPrice": 0.50}]
        assert interpolate_price(pricing, 1) == 0.50
        assert interpolate_price(pricing, 100) == 0.50
        assert interpolate_price(pricing, 999) == 0.50


# ===========================================================================
# find_variation
# ===========================================================================

class TestFindVariation:
    def test_match_by_dk_pn(self):
        product = SAMPLE_PRODUCT["Product"]
        var = find_variation(product, "475-BP104FAS-ZCT-ND")
        assert var["PackageType"]["Name"] == "Cut Tape (CT)"

    def test_match_different_variation(self):
        product = SAMPLE_PRODUCT["Product"]
        var = find_variation(product, "475-BP104FAS-ZTR-ND")
        assert var["PackageType"]["Name"] == "Tape & Reel (TR)"

    def test_fallback_no_target(self):
        product = SAMPLE_PRODUCT["Product"]
        var = find_variation(product)
        # Should return first non-marketplace variation with pricing
        assert var["DigiKeyProductNumber"] == "475-BP104FAS-ZTR-ND"

    def test_fallback_unknown_target(self):
        product = SAMPLE_PRODUCT["Product"]
        var = find_variation(product, "NONEXISTENT-ND")
        # Falls back to first non-marketplace variation with pricing
        assert var["DigiKeyProductNumber"] == "475-BP104FAS-ZTR-ND"

    def test_empty_variations(self):
        product = {"ProductVariations": []}
        assert find_variation(product) == {}


# ===========================================================================
# extract_fields
# ===========================================================================

class TestExtractFields:
    def test_basic_fields(self):
        fields = extract_fields(SAMPLE_PRODUCT, "475-BP104FAS-ZCT-ND")
        assert fields["DD"] == "Photodiode 880nm 20ns"
        assert fields["PD"] == "Photodiode"
        assert fields["DK"] == "475-BP104FAS-ZCT-ND"
        assert fields["MFR"] == "ams-OSRAM"
        assert fields["MPN"] == "BP 104 FAS-Z"
        assert fields["PKG"] == "Cut Tape (CT)"
        assert fields["_min_qty"] == 1

    def test_variation_specific_pricing(self):
        ct_fields = extract_fields(SAMPLE_PRODUCT, "475-BP104FAS-ZCT-ND")
        tr_fields = extract_fields(SAMPLE_PRODUCT, "475-BP104FAS-ZTR-ND")
        # Cut Tape starts at qty 1, Tape & Reel at qty 1500
        assert ct_fields["_pricing"][0]["BreakQuantity"] == 1
        assert tr_fields["_pricing"][0]["BreakQuantity"] == 1500

    def test_dd_falls_back_to_pd(self):
        data = {
            "Product": {
                "Description": {
                    "DetailedDescription": "",
                    "ProductDescription": "Fallback description",
                },
                "Manufacturer": {"Name": "Test"},
                "ManufacturerProductNumber": "TEST-1",
                "ProductUrl": "",
                "ProductVariations": [],
            }
        }
        fields = extract_fields(data)
        assert fields["DD"] == "Fallback description"

    def test_empty_product(self):
        fields = extract_fields({})
        assert fields["DK"] == "N/A"
        assert fields["MFR"] == "N/A"
        assert fields["PKG"] == "N/A"


# ===========================================================================
# format_custom
# ===========================================================================

class TestFormatCustom:
    def _fields(self, **overrides):
        """Helper to build a fields dict with sensible defaults."""
        base = {
            "DD": "Photodiode 880nm 20ns",
            "PD": "Photodiode",
            "DK": "475-BP104FAS-ZCT-ND",
            "MFR": "ams-OSRAM",
            "MPN": "BP 104 FAS-Z",
            "URL": "https://digikey.com/test",
            "PKG": "Cut Tape (CT)",
            "_pricing": SAMPLE_PRICING,
            "_min_qty": 1,
        }
        base.update(overrides)
        return base

    def test_simple_field(self):
        assert format_custom("MPN", self._fields()) == "BP 104 FAS-Z"

    def test_multiple_fields_with_punctuation(self):
        result = format_custom("MPN, MFR", self._fields())
        assert result == "BP 104 FAS-Z, ams-OSRAM"

    def test_price_at_quantity(self):
        result = format_custom("$P100", self._fields())
        assert result == "$0.4940"

    def test_price_between_breaks(self):
        result = format_custom("$P50", self._fields())
        assert result == "$0.6700"

    def test_bare_price_uses_min_qty(self):
        fields = self._fields(_min_qty=100)
        result = format_custom("$P", fields)
        assert result == "$0.4940"

    def test_no_collision_price_then_pd(self):
        # This was a real bug: price "0.9600" followed by PD replacement
        # would match "P" inside the price string
        result = format_custom("DK: PD, $P1", self._fields())
        assert result == "475-BP104FAS-ZCT-ND: Photodiode, $0.9600"

    def test_no_collision_mpn_in_price(self):
        # MPN shouldn't match inside substituted price values
        result = format_custom("$P1 - MPN", self._fields())
        assert result == "$0.9600 - BP 104 FAS-Z"

    def test_pkg_field(self):
        result = format_custom("DK (PKG)", self._fields())
        assert result == "475-BP104FAS-ZCT-ND (Cut Tape (CT))"

    def test_empty_pricing(self):
        fields = self._fields(_pricing=[])
        result = format_custom("$P100", fields)
        assert result == "$N/A"

    def test_all_codes_in_one_string(self):
        result = format_custom("DD|PD|DK|MFR|MPN|URL|PKG|$P1", self._fields())
        assert "Photodiode 880nm 20ns" in result
        assert "475-BP104FAS-ZCT-ND" in result
        assert "ams-OSRAM" in result
        assert "$0.9600" in result


# ===========================================================================
# parse_max
# ===========================================================================

class TestParseMax:
    def test_integer(self):
        assert parse_max("5") == 5

    def test_zero(self):
        assert parse_max("0") == 0

    def test_inf(self):
        assert parse_max("inf") == 0

    def test_none_string(self):
        assert parse_max("none") == 0

    def test_unlimited(self):
        assert parse_max("unlimited") == 0

    def test_case_insensitive(self):
        assert parse_max("INF") == 0
        assert parse_max("Inf") == 0

    def test_negative_raises(self):
        with pytest.raises(Exception):
            parse_max("-1")

    def test_garbage_raises(self):
        with pytest.raises(Exception):
            parse_max("abc")


# ===========================================================================
# apply_max_limit
# ===========================================================================

class TestApplyMaxLimit:
    def test_under_limit(self):
        parts = ["A", "B", "C"]
        assert apply_max_limit(parts, 5, False) == ["A", "B", "C"]

    def test_caps_at_max(self, capsys):
        parts = list("ABCDEFGHIJK")  # 11 items
        result = apply_max_limit(parts, 3, False)
        assert result == ["A", "B", "C"]
        assert "Warning" in capsys.readouterr().err

    def test_quiet_suppresses_warning(self, capsys):
        parts = list("ABCDEFGHIJK")
        result = apply_max_limit(parts, 3, False, quiet=True)
        assert result == ["A", "B", "C"]
        assert capsys.readouterr().err == ""

    def test_unlimited(self):
        parts = list("ABCDEFGHIJK")
        # max_results=0 means unlimited, caller skips apply_max_limit,
        # but if called directly it should not truncate
        result = apply_max_limit(parts, 0, False)
        assert result == parts

    def test_exact_at_max(self, capsys):
        parts = list("ABC")
        result = apply_max_limit(parts, 3, False)
        assert result == ["A", "B", "C"]
        assert capsys.readouterr().err == ""


# ===========================================================================
# resolve_part_numbers (non-network cases only)
# ===========================================================================

class TestResolvePartNumbers:
    def test_single_part(self):
        parts, total = resolve_part_numbers("475-BP104FAS-ZCT-ND", None, None)
        assert parts == ["475-BP104FAS-ZCT-ND"]
        assert total is None

    def test_comma_separated(self):
        parts, total = resolve_part_numbers("AAA, BBB, CCC", None, None)
        assert parts == ["AAA", "BBB", "CCC"]
        assert total is None

    def test_comma_strips_whitespace(self):
        parts, _ = resolve_part_numbers("  AAA ,BBB  , CCC  ", None, None)
        assert parts == ["AAA", "BBB", "CCC"]

    def test_comma_skips_empty(self):
        parts, _ = resolve_part_numbers("AAA,,BBB,", None, None)
        assert parts == ["AAA", "BBB"]

    def test_file_input(self, tmp_path):
        f = tmp_path / "parts.txt"
        f.write_text("PART-1\nPART-2\n\nPART-3\n")
        parts, total = resolve_part_numbers(str(f), None, None)
        assert parts == ["PART-1", "PART-2", "PART-3"]
        assert total is None
