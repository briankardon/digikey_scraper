# DigiKey Scraper

A command-line tool for looking up electronic component product information via the [DigiKey v4 API](https://developer.digikey.com/).

## Features

- Look up any component by DigiKey part number or manufacturer part number
- Multi-product lookup: comma-separated, file input, or wildcard patterns
- View descriptions, pricing, packaging, and manufacturer info
- Custom format strings for scripted/automated output
- Raw JSON output for further processing

## Prerequisites

- Python 3.8+
- A DigiKey API account with a **client ID** and **client secret** (register at [developer.digikey.com](https://developer.digikey.com/))

## Configuration

The tool needs DigiKey API credentials, which can be provided in two ways:

### Option 1: Config File (recommended)

Create a file at `secret/config.json` in the project root with the following structure:

```
digikey_scraper/
├── secret/
│   └── config.json      <-- put your credentials here
├── source/
│   └── digikey_lookup.py
└── ...
```

**`secret/config.json`** format:

```json
{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET"
}
```

> **Note:** The `secret/` directory is excluded from version control via `.gitignore`. Never commit your credentials.

### Option 2: Environment Variables

Set the following environment variables:

```bash
export DIGIKEY_CLIENT_ID="YOUR_CLIENT_ID"
export DIGIKEY_CLIENT_SECRET="YOUR_CLIENT_SECRET"
```

Environment variables take precedence over the config file.

## Usage

```bash
python source/digikey_lookup.py <part_number> [options]
```

### Basic Lookup

```bash
python source/digikey_lookup.py "BP 104 FAS-Z"
```

Example output:

```
Description:          Photodiode 880nm 20ns 120° 2-SMD, Gull Wing
DigiKey Part #:       475-BP104FAS-ZCT-ND
Manufacturer:         ams-OSRAM USA INC.
Manufacturer Part #:  BP 104 FAS-Z
Package Type:         Cut Tape (CT)
Quantity     Unit Price
--------     ----------
1             $   0.9600
10            $   0.6700
100           $   0.4940
```

### Multi-Product Lookup

**Comma-separated:**

```bash
python source/digikey_lookup.py "475-BP104FAS-ZCT-ND,475-BP104FAS-ZTR-ND"
```

**From a file** (one part number per line):

```bash
python source/digikey_lookup.py parts.txt
```

**Wildcard patterns** (uses DigiKey keyword search, then filters with glob matching):

```bash
python source/digikey_lookup.py "475-BP104FAS*"
```

### Result Limiting

By default, multi-product lookups are capped at 10 results to protect your API quota.

```bash
# Cap at 5 results
python source/digikey_lookup.py "475-BP104FAS*" --max 5

# No limit
python source/digikey_lookup.py "475-BP104FAS*" --max 0
python source/digikey_lookup.py "475-BP104FAS*" --max inf

# Interactive: prompt before proceeding if results exceed 10
python source/digikey_lookup.py "475-BP104FAS*" -i

# Suppress the truncation warning
python source/digikey_lookup.py "475-BP104FAS*" -q
```

### Raw JSON Output

```bash
python source/digikey_lookup.py "BP 104 FAS-Z" --json
```

Returns the full API response as formatted JSON, useful for debugging or piping into other tools.

### Custom Format Strings

Use `--fmt` to produce single-line output with specific fields:

```bash
python source/digikey_lookup.py "BP 104 FAS-Z" --fmt "MPN, $P100"
```

Output:

```
BP 104 FAS-Z, $0.4940
```

#### Format Codes

| Code   | Description                                        |
|--------|----------------------------------------------------|
| `DD`   | Detailed description                               |
| `PD`   | Short product description                          |
| `DK`   | DigiKey part number                                |
| `MFR`  | Manufacturer name                                  |
| `MPN`  | Manufacturer part number                           |
| `URL`  | Product URL on digikey.com                         |
| `PKG`  | Package type / variation (e.g. "Cut Tape (CT)")    |
| `P`    | Unit price at minimum order quantity               |
| `P<n>` | Unit price at quantity `<n>` (e.g., `P100`, `P15`) |

Price codes use the applicable price break: the highest break quantity at or below the requested quantity. If the requested quantity is below the first break, the first break price is used.

#### Format String Examples

```bash
# Description with price at qty 1
--fmt "DD: $P1"

# Tab-separated fields for spreadsheet import
--fmt "DK\tMPN\tMFR\t$P"

# Part number with packaging info
--fmt "DK (PKG): $P100"

# Just the product URL
--fmt "URL"
```

### Options Summary

| Option              | Description                                          |
|---------------------|------------------------------------------------------|
| `--json`            | Output raw JSON response                             |
| `--fmt FORMAT`      | One-line output using format codes                   |
| `--max N`           | Cap results at N (default: 10). 0 or inf = no limit  |
| `-i`, `--interactive` | Prompt before looking up more than 10 results      |
| `-q`, `--quiet`     | Suppress warnings                                    |

## Project Structure

```
digikey_scraper/
├── source/
│   └── digikey_lookup.py   # Main script
├── secret/
│   └── config.json         # API credentials (not tracked by git)
├── .gitignore
└── README.md
```
