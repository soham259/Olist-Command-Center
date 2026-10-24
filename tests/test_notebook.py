"""
Executes notebooks/Olist_Analysis.ipynb top to bottom (needs PostgreSQL with
the pipeline already run) and checks it finishes without errors and still
shows the verified headline figures.
"""
from pathlib import Path

import nbformat
import pytest

nbclient = pytest.importorskip("nbclient")

NOTEBOOK = Path(__file__).resolve().parent.parent / "notebooks" / "Olist_Analysis.ipynb"


@pytest.mark.db
def test_notebook_runs_and_shows_verified_results():
    nb = nbformat.read(NOTEBOOK, as_version=4)
    nbclient.NotebookClient(nb, timeout=300, kernel_name="python3",
                            resources={"metadata": {"path": str(NOTEBOOK.parent)}}).execute()
    outputs = [o for c in nb.cells if c.cell_type == "code" for o in c.get("outputs", [])]
    assert not [o for o in outputs if o.output_type == "error"]
    assert sum("image/png" in o.get("data", {}) for o in outputs) >= 12
    text = "\n".join(o.get("data", {}).get("text/markdown", "") + o.get("data", {}).get("text/html", "") for o in outputs)
    for expected in ("13,221,498.11", "96,478", "14.33%", "1.77×", "207 sellers", "8.52%", "2.19%", "0 failed"):
        assert expected in text, f"{expected} missing from notebook output"
