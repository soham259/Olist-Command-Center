# Data

## Source

Olist Brazilian E-Commerce Public Dataset, originally published on Kaggle by
Olist: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

Kaggle lists the dataset under a CC BY-NC-SA 4.0 license. That license permits
non-commercial reuse with attribution, but it does not on its own establish
that Olist has granted broad redistribution rights over the raw CSVs
themselves — so this repository does not commit the raw data. Treat the
license note above as what's stated on the dataset's own page, not as
something independently verified here.

The CSVs used to build this project were sourced from a public GitHub mirror
of the dataset rather than downloaded directly from Kaggle, and were checked
against the dataset's well-known public row counts before use (see
`docs/data_dictionary.md` for the verification table). If you download the
files yourself directly from Kaggle, you should get the same row counts as
the table below.

**Dataset revision note (2026-10 audit):** the reviews file exists in two
published revisions — 100,000 rows (used when this project's documentation
was first written) and 99,224 rows (the revision supplied for the audit). The
pipeline is validated against the 99,224-row file; the other 8 files match
in both. The expected counts live in one place, `scripts/config.py`
(`EXPECTED_ROW_COUNTS`).

## Expected files

Place the following 9 files in this repository's `raw_data/` directory
(create the directory if it doesn't exist):

| File | Expected rows |
|---|---:|
| `olist_customers_dataset.csv` | 99,441 |
| `olist_orders_dataset.csv` | 99,441 |
| `olist_order_items_dataset.csv` | 112,650 |
| `olist_order_payments_dataset.csv` | 103,886 |
| `olist_order_reviews_dataset.csv` | 99,224 |
| `olist_products_dataset.csv` | 32,951 |
| `olist_sellers_dataset.csv` | 3,095 |
| `olist_geolocation_dataset.csv` | 1,000,163 |
| `product_category_name_translation.csv` | 71 |

`scripts/run_pipeline.py` checks these row counts before doing anything else
and stops if a file is missing or doesn't match. `scripts/verify_schema.py`
additionally checks every file's column names.

**Folder convention:** one copy of the CSVs, in `<project root>/raw_data/`,
unzipped, with the exact filenames above. (Set `OLIST_RAW_DIR` in `.env` only
if you deliberately keep them elsewhere.)

## Why raw data isn't committed to this repository

`raw_data/*.csv` is excluded via `.gitignore`. This isn't a statement that the
data is sensitive — it's that redistribution rights for the raw dataset
aren't clearly established, so the safer default is not to publish it. Every
number in this project's documentation is instead reported directly (tables,
summary statistics, KPI values), so the analysis is readable without needing
the raw files — you only need them to re-run the pipeline yourself.

## How to get the data

1. Download the 9 CSVs from the Kaggle page linked above (requires a free
   Kaggle account), or from another source you trust to be identical.
2. Place them directly in `raw_data/` using the exact filenames listed above.
3. Run `python3 scripts/verify_schema.py` to sanity-check the files, or go
   straight to `python3 scripts/run_pipeline.py` (see the main README for the
   full reproduction steps).
