#!/usr/bin/env python3
"""Command-line tool to look up DigiKey product info via the v4 API."""

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
PRODUCT_DETAILS_URL = "https://api.digikey.com/products/v4/search/{productNumber}/productdetails"

# Field codes for --fmt format strings:
#   DD  = Detailed description
#   PD  = Short product description
#   DK  = DigiKey part number
#   MFR = Manufacturer name
#   MPN = Manufacturer part number
#   URL = Product URL
#   P<n> = Unit price at quantity <n> (uses applicable price break)
#   P    = Unit price at minimum order quantity


def get_credentials():
    """Load client ID and secret from environment variables or config file."""
    client_id = os.environ.get("DIGIKEY_CLIENT_ID")
    client_secret = os.environ.get("DIGIKEY_CLIENT_SECRET")

    if client_id and client_secret:
        return client_id, client_secret

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "secret", "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)
        return config["client_id"], config["client_secret"]

    print("Error: DigiKey API credentials not found.", file=sys.stderr)
    print("Set DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET environment variables,", file=sys.stderr)
    print(f"or create {config_path} with client_id and client_secret fields.", file=sys.stderr)
    sys.exit(1)


def get_oauth_token(client_id, client_secret):
    """Get an OAuth2 token using client credentials flow."""
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Error getting OAuth token: {e.code} {e.reason}", file=sys.stderr)
        print(body, file=sys.stderr)
        sys.exit(1)


def lookup_product(part_number, client_id, token):
    """Call the ProductDetails API and return the response dict."""
    url = PRODUCT_DETAILS_URL.format(productNumber=urllib.parse.quote(part_number, safe=""))

    req = urllib.request.Request(url, headers={
        "X-DIGIKEY-Client-Id": client_id,
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Locale-Language": "en",
        "X-DIGIKEY-Locale-Currency": "USD",
        "X-DIGIKEY-Locale-Site": "US",
    })

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"API error: {e.code} {e.reason}", file=sys.stderr)
        print(body, file=sys.stderr)
        sys.exit(1)


def interpolate_price(pricing, qty):
    """Find the unit price for a given quantity by using the applicable price break."""
    if not pricing:
        return None
    # Price breaks are thresholds: use the highest break quantity <= qty
    applicable = None
    for pb in pricing:
        if pb.get("BreakQuantity", 0) <= qty:
            applicable = pb
    # If qty is below the first break, use the first break price
    if applicable is None:
        applicable = pricing[0]
    return applicable.get("UnitPrice")


def get_dk_part_and_pricing(product):
    """Get the DK part number and pricing from the first non-marketplace variation."""
    for var in product.get("ProductVariations", []):
        if not var.get("MarketPlace", False):
            dk_part = var.get("DigiKeyProductNumber", "N/A")
            pricing = var.get("StandardPricing", [])
            min_qty = var.get("MinimumOrderQuantity", 1)
            if pricing:
                return dk_part, pricing, min_qty
    return "N/A", [], 1


def extract_fields(data):
    """Extract all field values from API response into a dict."""
    product = data.get("Product", {})
    description = product.get("Description", {})
    dk_part, pricing, min_qty = get_dk_part_and_pricing(product)
    return {
        "DD": description.get("DetailedDescription", "") or description.get("ProductDescription", ""),
        "PD": description.get("ProductDescription", ""),
        "DK": dk_part,
        "MFR": product.get("Manufacturer", {}).get("Name", "N/A"),
        "MPN": product.get("ManufacturerProductNumber", "N/A"),
        "URL": product.get("ProductUrl", "N/A"),
        "_pricing": pricing,
        "_min_qty": min_qty,
    }


def format_custom(fmt, fields):
    """Replace field codes in a format string with their values."""
    # Replace P<digits> and bare P with price values
    def replace_price(m):
        if m.group(1):
            qty = int(m.group(1))
        else:
            qty = fields["_min_qty"]
        price = interpolate_price(fields["_pricing"], qty)
        if price is None:
            return "N/A"
        return f"{price:.4f}"

    result = re.sub(r"P(\d+)?", replace_price, fmt)

    # Replace fixed codes longest-first to avoid partial matches (MFR before MF, etc.)
    for code in sorted(("DD", "PD", "DK", "MFR", "MPN", "URL"), key=len, reverse=True):
        result = result.replace(code, str(fields.get(code, "N/A")))

    return result


def format_output(fields):
    """Format and print the product details (default multi-line output)."""
    print(f"Description:          {fields['DD']}")
    print(f"DigiKey Part #:       {fields['DK']}")
    print(f"Manufacturer:         {fields['MFR']}")
    print(f"Manufacturer Part #:  {fields['MPN']}")

    pricing = fields["_pricing"]
    if pricing:
        print(f"{'Quantity':<12} {'Unit Price':>10}")
        print(f"{'--------':<12} {'----------':>10}")
        for pb in pricing[:3]:
            qty = pb.get("BreakQuantity", "")
            price = pb.get("UnitPrice", 0)
            print(f"{qty:<12} ${price:>9.4f}")
    else:
        print("Pricing:              N/A")


def main():
    parser = argparse.ArgumentParser(
        description="Look up DigiKey product info by part number."
    )
    parser.add_argument(
        "part_number",
        help="DigiKey or manufacturer part number"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON response"
    )
    parser.add_argument(
        "--fmt",
        help="One-line output format using field codes: DD, PD, DK, MFR, MPN, URL, P<qty>, P. "
             "P with no number gives the price at minimum order qty. "
             "Example: 'DD: $P15' outputs the description, colon, space, dollar sign, and price at qty 15."
    )
    args = parser.parse_args()

    client_id, client_secret = get_credentials()
    token = get_oauth_token(client_id, client_secret)
    data = lookup_product(args.part_number, client_id, token)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        fields = extract_fields(data)
        if args.fmt:
            print(format_custom(args.fmt, fields))
        else:
            format_output(fields)


if __name__ == "__main__":
    main()
