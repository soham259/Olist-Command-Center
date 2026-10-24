# Windows Runbook

From a ZIP of this repository to a fully built database and a green test run
on Windows 10/11. Each stage ends with a check: don't move to the next stage
until the check passes.

All commands are for **PowerShell** (Start menu → type "PowerShell"). The
examples assume the project lives in `C:\Projects\Olist-Command-Center` —
substitute your own path.

---

## Stage 1 — Check what's already installed

```powershell
python --version
pip --version
git --version
psql --version
Get-Service *postgres*
```

| Output | Meaning | Action |
|---|---|---|
| `Python 3.11.x` – `3.13.x` | Good | — |
| `Python was not found` or opens the Microsoft Store | Not installed | Install from python.org (Windows installer, 64-bit). On the first screen tick **"Add python.exe to PATH"**. Close and reopen PowerShell. |
| `git` not recognised | Not installed | Optional — only needed to clone/push. Install from git-scm.com with defaults. |
| `psql` not recognised but `Get-Service` shows `postgresql-x64-16` (or 15/17) | PostgreSQL installed, not on PATH | See Stage 3, "Put psql on PATH" |
| `Get-Service` shows nothing | PostgreSQL not installed | Stage 3 |
| Service `Status` = `Stopped` | Installed but not running | `Start-Service postgresql-x64-16` (use the exact name shown; run PowerShell as Administrator) |

---

## Stage 2 — Lay out the files

1. Extract the repository ZIP to `C:\Projects\`. If it creates a nested
   folder (`Olist-Command-Center-main\Olist-Command-Center-main\`), move the
   inner folder up so `README.md` sits directly in
   `C:\Projects\Olist-Command-Center\`.
2. Create the data folder and put **unzipped** copies of the 9 CSVs in it —
   keep your original downloads untouched elsewhere:

```powershell
cd C:\Projects\Olist-Command-Center
mkdir raw_data
# copy/extract the 9 .csv files into raw_data\  (right-click each .zip → Extract All, then move the .csv)
Get-ChildItem raw_data\*.csv | Select-Object Name, Length
```

**Check:** exactly these 9 names, no `.zip`, no duplicates like
`olist_orders_dataset (1).csv`:

```
olist_customers_dataset.csv            olist_order_reviews_dataset.csv
olist_geolocation_dataset.csv          olist_orders_dataset.csv
olist_order_items_dataset.csv          olist_products_dataset.csv
olist_order_payments_dataset.csv       olist_sellers_dataset.csv
product_category_name_translation.csv
```

---

## Stage 3 — PostgreSQL

**Install (only if Stage 1 showed none):** download the PostgreSQL 16
Windows installer (EDB) from postgresql.org → Download → Windows. Accept the
defaults; components needed: *PostgreSQL Server* and *Command Line Tools*
(pgAdmin is optional; Stack Builder is not needed). It asks for a password
for the `postgres` superuser — choose one and remember it. Keep port
**5432** unless the installer says it is taken (then it suggests 5433 — note
whichever it uses).

**Put psql on PATH (current window only):**

```powershell
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"
psql --version
```

(To make it permanent: Start → "Edit the system environment variables" →
Environment Variables → Path → New → `C:\Program Files\PostgreSQL\16\bin`.)

**Create a dedicated database:**

```powershell
createdb -U postgres -p 5432 olist
psql -U postgres -p 5432 -d olist -c "SELECT current_database(), version();"
```

**Check:** prints `olist` and a PostgreSQL version. Use a database that
holds nothing else: the pipeline drops and recreates the `raw` and
`analytics` schemas inside it.

| Error | Fix |
|---|---|
| `password authentication failed for user "postgres"` | Wrong password — retype it; it is the one chosen during install |
| `could not connect to server: Connection refused` | Service stopped (Stage 1 table) or wrong port (`-p 5433`) |
| `database "olist" already exists` | Fine if it's this project's; otherwise pick another name (e.g. `olist_project`) and use it below |

---

## Stage 4 — Python environment

```powershell
cd C:\Projects\Olist-Command-Center
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python -c "import pandas, sqlalchemy, psycopg2, pytest; print('ok', pandas.__version__, sqlalchemy.__version__)"
```

**Check:** prompt starts with `(.venv)` and the last line prints `ok ...`.

If activation fails with "running scripts is disabled on this system":

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then rerun `.venv\Scripts\Activate.ps1`. Every new PowerShell window needs
`cd` + activation again before running the project.

---

## Stage 5 — Configure the connection

```powershell
Copy-Item .env.example .env
notepad .env
```

Edit the last line to your password (and port/database name if different):

```
OLIST_DB_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/olist
```

If the password contains `@ : / ? # %`, URL-encode it (`@` → `%40`, `#` → `%23`).
`.env` is gitignored — never commit it.

**Check:**

```powershell
python -c "import sys; sys.path.insert(0,'scripts'); import config; print(config.masked_db_url()); print(config.RAW_DIR)"
```

Shows your URL with `***` for the password and the `raw_data` path.

---

## Stage 6 — Pre-flight check of the CSVs

```powershell
python scripts\verify_schema.py
```

Profiles each file (row count, columns, nulls, duplicates, date ranges) and
ends with **`SCHEMA CHECK PASSED`**. It checks structure and row counts, not
values. If it fails, it lists every problem:

| Message | Fix |
|---|---|
| `MISSING FILE: ...` | Name/location wrong — compare with Stage 2 |
| `ROW COUNT MISMATCH` on reviews (100,000) | You have the older revision of the reviews file. Use the 99,224-row file this project is validated against. |
| `COLUMN MISMATCH` | Wrong file or a file re-saved by Excel — re-extract the original CSV (don't open and save CSVs in Excel) |

---

## Stage 7 — Run the pipeline

```powershell
python scripts\run_pipeline.py
```

Takes about 2–5 minutes. **First line to read:** `Target database: ...` —
confirm it's the project database before it gets to step 2.

Expected milestones:

```
STEP 1 complete: all 9 source files verified.
  raw.geolocation  loaded=1,000,163 rows [OK]
STEP 2 complete: raw schema loaded and row-count verified.
STEP 3 complete: constraints applied without violation ...
STEP 4 complete: all referential integrity gates passed.
  Revenue reconciliation: fact_order_items=13221498.11  fact_orders=13221498.11  [MATCH]
STEP 5 complete: star schema built and reconciled.
  Total source rows loaded: 1,550,922 rows across 9 raw tables
STEP 6 complete: 16 scorecard lines.
STEP 7 complete: CSV export refreshed.
Pipeline completed successfully in ... seconds
```

A log is also written to `logs\pipeline_<timestamp>.log`. Any failure prints
`PIPELINE FAILED: <reason>` naming the step/SQL file, rolls back that file,
and exits with code 1 (`echo $LASTEXITCODE`). It is safe to rerun after
fixing the cause — the pipeline rebuilds everything from scratch each run.

---

## Stage 8 — Run the tests

```powershell
pytest -v
```

**Check:** last line `81 passed`. (`pytest tests\test_data_quality.py -v`
runs only the original 37; `pytest -m "not db"` runs the 18 tests that need
no database.)

---

## Stage 8b — Generate all charts and tables

```powershell
python scripts\generate_visuals.py
start reports\report.html
```

**Check:** it ends with `Charts: 15   Tables: 14   Data-quality: 27 pass /
9 warn / 0 fail`, and the report opens in your browser. Charts are in
`reports\charts\`, tables in `reports\tables\`. If it says the analytics
views are missing, run the pipeline (Stage 7) first.

---

## Stage 8c — Open the analysis notebook

```powershell
jupyter notebook notebooks\Olist_Analysis.ipynb
```

Your browser opens Jupyter. Choose **Run → Run All Cells**. Each section shows
its SQL, a table, a chart and a **Result** line; section 9 summarises every
finding. The notebook is saved with outputs, so you can also just read it on
GitHub. If the first cell fails with a connection error, check `.env` (Stage 5)
and that the pipeline has been run (Stage 7).

---

## Stage 9 — Look at the results yourself

```powershell
psql -U postgres -d olist
```

Then inside `psql`:

```sql
SELECT * FROM analytics.v_row_inventory;
SELECT COUNT(*), SUM(item_revenue) FROM analytics.fact_orders WHERE order_status = 'delivered';
SELECT * FROM analytics.v_region_late_rate ORDER BY late_pct DESC;
SELECT * FROM analytics.v_state_late_rate WHERE region = 'Nordeste' ORDER BY late_pct DESC;
SELECT * FROM analytics.v_seller_quadrant_summary ORDER BY basis, total_revenue DESC;
SELECT * FROM analytics.v_customer_spend_tier ORDER BY spend_tier;
SELECT * FROM analytics.v_repeat_by_first_order_tier ORDER BY 1;
\q
```

Run the investigation scripts (read-only):

```powershell
psql -U postgres -d olist -f sql\02_data_quality_audit.sql
psql -U postgres -d olist -f sql\04_sql_foundation.sql
psql -U postgres -d olist -f sql\05_advanced_sql.sql
```

---

## Stage 10 — (Optional) Rebuild the business-case document

Needs Node.js LTS from nodejs.org.

```powershell
cd business_case
npm install
node build_business_case.js
cd ..
```

---

## Stage 11 — Clean re-run from scratch

To prove nothing depends on leftovers:

```powershell
dropdb -U postgres olist
createdb -U postgres olist
python scripts\run_pipeline.py
pytest tests -v
```
