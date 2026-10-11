# PlanWise-Agent

PlanWise is a Streamlit event-planning app with budget, occasion-aware vendor, and weather-risk recommendations. Vendor retrieval uses persistent ChromaDB vectors combined with deterministic city, capacity, occasion, and budget ranking.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Catalogue behavior

The repository includes `data/vendor_catalog.json`, including each catalog record's contact and website fields. These details are catalog-provided examples and have not been independently verified; confirm vendor identity, contact information, pricing, and availability before relying on them for a real event. Do not add private credentials or personal contact information without permission.

PlanWise loads `data/vendor_catalog.json` when it exists. If that file is absent, the application automatically uses `data/sample_vendor_catalog.json`, which contains clearly fictional vendor names and contact details. The app displays a “Using sample catalogue” notice in this case. The sample data is suitable for demonstrations and tests, not real bookings.

The catalog must contain a top-level `vendors` array. Records include `id`, `name`, `category`, `location`, `locality`, `capacity`, `cost_per_day`, `type`, `rating`, `amenities`, `description`, `tags`, `search_text`, `website`, `contact`, `suitable_for`, `vibe`, and `menu_recommendations`.

## Rebuild the vector index

The persistent collection is named `vendors` and defaults to `.chroma/`. To rebuild or update it after editing the catalog, run this from the project root:

```powershell
.\.venv\Scripts\python.exe -c "from src.tools.rag_tool import build_vector_index; print(build_vector_index())"
```

The operation upserts catalog records by ID, so repeated runs update existing records rather than duplicating them. Embeddings are generated locally using deterministic feature hashing; indexing and tests do not require an embedding API or network access. Normal vendor searches build the index automatically on first use if the collection is missing or empty. If ChromaDB is unavailable or fails, search falls back to deterministic JSON ranking and marks results as `rules-only`.

Run the test suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_cases.py
```

Keep credentials in a local `.env` file or Streamlit secrets file; do not commit them.
