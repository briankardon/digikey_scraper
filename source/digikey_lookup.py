#!/usr/bin/env python3
"""Command-line tool to look up DigiKey product info via the v4 API."""

import argparse
import fnmatch
import json
import os
import re
import sys
import urllib.parse
import urllib.request

TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
PRODUCT_DETAILS_URL = "https://api.digikey.com/products/v4/search/{productNumber}/productdetails"
KEYWORD_SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"

# Field codes for --fmt format strings:
#   DD  = Detailed description
#   PD  = Short product description
#   DK  = DigiKey part number
#   MFR = Manufacturer name
#   MPN = Manufacturer part number
#   URL = Product URL
#   P<n> = Unit price at quantity <n> (uses applicable price break)
#   P    = Unit price at minimum order quantity

DEFAULT_MAX = 10


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


def api_headers(client_id, token):
    """Return standard headers for DigiKey API requests."""
    return {
        "X-DIGIKEY-Client-Id": client_id,
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Locale-Language": "en",
        "X-DIGIKEY-Locale-Currency": "USD",
        "X-DIGIKEY-Locale-Site": "US",
    }


def lookup_product(part_number, client_id, token):
    """Call the ProductDetails API and return the response dict."""
    url = PRODUCT_DETAILS_URL.format(productNumber=urllib.parse.quote(part_number, safe=""))
    req = urllib.request.Request(url, headers=api_headers(client_id, token))

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"API error for {part_number}: {e.code} {e.reason}", file=sys.stderr)
        print(body, file=sys.stderr)
        return None


def keyword_search(keyword, client_id, token, limit=50):
    """Search DigiKey by keyword and return list of matching DK part numbers."""
    body = json.dumps({
        "Keywords": keyword,
        "Limit": limit,
        "Offset": 0,
    }).encode()

    headers = api_headers(client_id, token)
    headers["Content-Type"] = "application/json"
    req = urllib.request.Request(KEYWORD_SEARCH_URL, data=body, headers=headers)

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Search API error: {e.code} {e.reason}", file=sys.stderr)
        print(body, file=sys.stderr)
        sys.exit(1)

    part_numbers = set()
    for product in data.get("Products", []):
        # Use the top-level manufacturer part number as the lookup key,
        # since product details are per-product, not per-variation.
        # But collect variation DK part numbers for glob matching.
        for var in product.get("ProductVariations", []):
            dk_pn = var.get("DigiKeyProductNumber")
            if dk_pn:
                part_numbers.add(dk_pn)
    return sorted(part_numbers)


def resolve_part_numbers(input_str, client_id, token):
    """Resolve the input into a list of part numbers.

    Handles:
      - File path (one part number per line)
      - Wildcard patterns (* or ?) via keyword search
      - Comma-separated list
      - Single part number
    """
    # Check if it's a file
    if os.path.isfile(input_str):
        with open(input_str) as f:
            parts = [line.strip() for line in f if line.strip()]
        return parts, None

    # Check for wildcard characters
    if "*" in input_str or "?" in input_str:
        # Strip wildcards to get the keyword for searching
        keyword = input_str.replace("*", "").replace("?", "")
        if not keyword:
            print("Error: wildcard pattern must contain some non-wildcard characters.", file=sys.stderr)
            sys.exit(1)
        all_matches = keyword_search(keyword, client_id, token)
        # Filter by the glob pattern (case-insensitive)
        pattern = input_str.upper()
        matches = [pn for pn in all_matches if fnmatch.fnmatch(pn.upper(), pattern)]
        return matches, len(all_matches)

    # Comma-separated list
    if "," in input_str:
        return [p.strip() for p in input_str.split(",") if p.strip()], None

    # Single part number
    return [input_str], None


def apply_max_limit(part_numbers, max_results, interactive, total_search_results=None):
    """Apply --max / --interactive limits. Returns the (possibly truncated) list."""
    count = len(part_numbers)

    if interactive:
        if count > DEFAULT_MAX:
            msg = f"Found {count} matching parts"
            if total_search_results and total_search_results > count:
                msg += f" (from {total_search_results} search results)"
            msg += f". Look up all {count}? [y/N] "
            answer = input(msg).strip().lower()
            if answer not in ("y", "yes"):
                print("Aborted.", file=sys.stderr)
                sys.exit(0)
        return part_numbers

    if max_results is not None and max_results > 0 and count > max_results:
        print(f"Warning: {count} parts found, capping at --max {max_results}. "
              f"Use --max 0 for no limit or -i for interactive confirmation.",
              file=sys.stderr)
        return part_numbers[:max_results]

    return part_numbers


def interpolate_price(pricing, qty):
    """Find the unit price for a given quantity by using the applicable price break."""
    if not pricing:
        return None
    applicable = None
    for pb in pricing:
        if pb.get("BreakQuantity", 0) <= qty:
            applicable = pb
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
    # Use placeholder-based substitution to avoid codes matching inside
    # already-substituted values (e.g. "PD" matching inside a price string).
    placeholders = {}
    counter = [0]

    def make_placeholder(value):
        key = f"\x00{counter[0]}\x00"
        counter[0] += 1
        placeholders[key] = value
        return key

    # Replace fixed codes longest-first to avoid partial matches
    result = fmt
    for code in sorted(("DD", "PD", "DK", "MFR", "MPN", "URL"), key=len, reverse=True):
        result = result.replace(code, make_placeholder(str(fields.get(code, "N/A"))))

    # Replace P<digits> and bare P with price values
    def replace_price(m):
        if m.group(1):
            qty = int(m.group(1))
        else:
            qty = fields["_min_qty"]
        price = interpolate_price(fields["_pricing"], qty)
        if price is None:
            return make_placeholder("N/A")
        return make_placeholder(f"{price:.4f}")

    result = re.sub(r"P(\d+)?", replace_price, result)

    # Swap placeholders for actual values
    for key, value in placeholders.items():
        result = result.replace(key, value)

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


def output_product(data, args):
    """Output a single product's data according to the chosen format."""
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        fields = extract_fields(data)
        if args.fmt:
            print(format_custom(args.fmt, fields))
        else:
            format_output(fields)


def parse_max(value):
    """Parse --max value: 0 means unlimited, positive int is the cap."""
    if value.lower() in ("inf", "none", "unlimited", "0"):
        return 0
    try:
        n = int(value)
        if n < 0:
            raise argparse.ArgumentTypeError("--max must be 0 (unlimited) or a positive integer")
        return n
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid --max value: {value}")


def main():
    parser = argparse.ArgumentParser(
        description="Look up DigiKey product info by part number."
    )
    parser.add_argument(
        "part_number",
        help="DigiKey part number, comma-separated list, file path (one per line), "
             "or wildcard pattern (e.g. 475-BP104FAS*)"
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
    parser.add_argument(
        "--max", type=parse_max, default=DEFAULT_MAX, dest="max_results",
        help=f"Max number of products to look up (default: {DEFAULT_MAX}). "
             "Use --max 0 or --max inf for no limit."
    )
    parser.add_argument(
        "-i", "--interactive", action="store_true",
        help="Prompt for confirmation when results exceed the default limit, overrides --max."
    )
    args = parser.parse_args()

    client_id, client_secret = get_credentials()
    token = get_oauth_token(client_id, client_secret)

    part_numbers, total_search = resolve_part_numbers(args.part_number, client_id, token)

    if not part_numbers:
        print("No matching part numbers found.", file=sys.stderr)
        sys.exit(1)

    if args.interactive:
        part_numbers = apply_max_limit(part_numbers, None, True, total_search)
    elif args.max_results != 0:
        part_numbers = apply_max_limit(part_numbers, args.max_results, False, total_search)

    separator_needed = not args.fmt and len(part_numbers) > 1
    first = True
    for pn in part_numbers:
        if separator_needed:
            if not first:
                print()
            print(f"=== {pn} ===")
        first = False

        data = lookup_product(pn, client_id, token)
        if data is None:
            continue
        output_product(data, args)


if __name__ == "__main__":
    main()
