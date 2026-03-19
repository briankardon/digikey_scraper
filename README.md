# DigiKey Scraper

A command-line tool for looking up electronic component product information via the [DigiKey v4 API](https://developer.digikey.com/).

## Features

- Look up any component by DigiKey part number or manufacturer part number
- View descriptions, pricing, and manufacturer info
- Custom format strings for scripted/automated output
- Raw JSON output for further processing

## Prerequisites

- Python 3.6+
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
Quantity     Unit Price
--------     ----------
1             $   0.9600
10            $   0.6700
100           $   0.4940
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
| `P`    | Unit price at minimum order quantity               |
| `P<n>` | Unit price at quantity `<n>` (e.g., `P100`, `P15`) |

Price codes use the applicable price break: the highest break quantity at or below the requested quantity. If the requested quantity is below the first break, the first break price is used.

#### Format String Examples

```bash
# Description with price at qty 1
--fmt "DD: $P1"

# Tab-separated fields for spreadsheet import
--fmt "DK\tMPN\tMFR\t$P"

# Just the product URL
--fmt "URL"
```

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
