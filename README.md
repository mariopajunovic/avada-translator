# Avada Translator

A Python toolkit for extracting, translating, and re-assembling Avada/Fusion Builder content using OpenAI.

## Overview

This toolset processes WordPress Avada theme content exported as `.txt` files containing Fusion Builder shortcodes. It extracts translatable text segments, sends them to OpenAI for translation, and reassembles the translated content back into the original structure.

## Requirements

- Python 3.8+
- OpenAI API key
- Required packages:
  ```bash
  pip install openai pydantic
  ```

## Environment Setup

```bash
export OPENAI_API_KEY='your-api-key-here'
```

## Preparing Source Files

**Important:** You must manually export the page content from WordPress/Avada:

1. Open the page in WordPress admin (Avada Live or Backend editor)
2. Switch to "Code" view to see the raw Fusion Builder shortcodes
3. Copy the entire page content
4. Save it as a `.txt` file in your source folder (e.g., `products/page-name.txt`)

This approach **speeds up translation by ~90%** and **reduces costs significantly** compared to translating in WordPress directly:
- Only translatable text is sent to OpenAI (not the entire page structure)
- Batch processing handles multiple pages in parallel
- Shortcodes and HTML remain untouched, eliminating formatting errors
- Fewer API tokens used = lower OpenAI costs

## Quick Start

```bash
python3 pipeline.py --src products/ --lang "German"
```

This creates a job folder in `jobs/german_YYYY-MM-DD_HH-MM/` with all outputs.

## Scripts

### `pipeline.py` - Main Pipeline

Orchestrates the entire translation workflow. Each run creates a new job folder.

```bash
python3 pipeline.py --src products/ --lang "German" --model gpt-4o-mini --workers 12 --batch 40
```

**Arguments:**
| Argument | Default | Description |
|----------|---------|-------------|
| `--src` | `products` | Source folder with .txt files |
| `--lang` | `English` | Target language |
| `--model` | `gpt-5-mini` | OpenAI model |
| `--workers` | `12` | Parallel workers |
| `--batch` | `40` | Segments per API request |
| `--overwrite` | `false` | Overwrite existing translations |
| `--job-name` | auto | Custom job name |

### `extract.py` - Container Extraction

Extracts `[fusion_builder_container]` blocks from source files.

```bash
# Single file
python3 extract.py export --input page.txt --out exported/

# Batch export
python3 extract.py product_export --src products/ --out containers/ --print-each
```

### `segments.py` - Segment Extraction & Application

Extracts translatable segments and applies translations back.

```bash
# Extract segments to JSON
python3 segments.py extract --src containers/ --out extracted/

# Apply translations
python3 segments.py apply \
  --src containers/ \
  --extracted extracted/ \
  --translated translated/ \
  --out applied/
```

### `translate.py` - Translation Engine

Translates extracted JSON segments using OpenAI API.

```bash
python3 translate.py \
  --in extracted/ \
  --out translated/ \
  --lang "German" \
  --model gpt-4o-mini \
  --workers 8 \
  --batch 40
```

### `merge.py` - Container Merging

Merges translated containers back into page files.

```bash
python3 merge.py --src applied/ --out output/
```

## Workflow

```
Source .txt files
       │
       ▼
   extract.py      → containers/
       │
       ▼
   segments.py     → extracted/ (JSON)
       │
       ▼
   translate.py    → translated/ (JSON)
       │
       ▼
   segments.py     → applied/
       │
       ▼
   merge.py        → output/ (final .txt)
```

## Job Directory Structure

Each pipeline run creates a self-contained folder:

```
jobs/
  german_2024-01-12_14-30/
    containers/     # Extracted Fusion containers
    extracted/      # Translatable segments (JSON)
    translated/     # Translated segments (JSON)
    applied/        # Containers with translations
    output/         # Final merged .txt files
```

## Notes

- Shortcodes, HTML tags, URLs, and CSS values are preserved during translation
- The translation engine validates that shortcode structure remains intact
- Failed translations are retried with exponential backoff
- Each job is independent and won't overwrite previous runs

## Disclaimer

This tool may occasionally produce translation errors or formatting issues. Always review the output before importing back to WordPress. Feel free to modify and adapt the scripts to your specific needs.

## License

MIT
