"""
CSV -> PostgreSQL raw layer ingestion (standalone).

Runs Steps 1-4 of scripts/run_pipeline.py only — validate source files,
(re)build and load the raw schema, apply FK constraints and indexes, and run
the referential-integrity gate — without building the star schema. Use it
when you want to (re)load the raw layer on its own.

It reuses the pipeline's own step functions rather than keeping a second copy
of the loading logic. (The previous standalone version kept its own copy,
which had drifted: it used `TRUNCATE` on tables referenced by foreign keys,
which PostgreSQL refuses once sql/03 has been applied, and it never re-applied
the constraints afterwards.)

WARNING: this drops and recreates the `raw` schema (and, via CASCADE, any
`analytics` objects that depend on it) in the database named by OLIST_DB_URL.
Use a dedicated project database.

Run with: python scripts/ingest_raw.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine  # noqa: E402

from config import DB_URL, masked_db_url  # noqa: E402
from run_pipeline import (  # noqa: E402
    setup_logging, step_apply_constraints, step_build_raw_schema,
    step_data_quality_gate, step_validate_source_files,
)


def main():
    log = setup_logging()
    log.info(f"Target database: {masked_db_url()}")
    engine = None
    try:
        step_validate_source_files(log)
        engine = create_engine(DB_URL)
        step_build_raw_schema(engine, log)
        step_apply_constraints(engine, log)
        step_data_quality_gate(engine, log)
    except Exception as e:
        log.error(f"INGESTION FAILED: {e}")
        sys.exit(1)
    finally:
        if engine is not None:
            engine.dispose()
    log.info("Raw layer loaded, row counts verified, constraints applied.")


if __name__ == "__main__":
    main()
