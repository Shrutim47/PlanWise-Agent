# PlanWise

PlanWise is a Streamlit event-planning app with budget, vendor, and weather-risk recommendations.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The vendor catalog is intentionally not included because its contact details have not been cleared for public release. To enable vendor recommendations, provide a reviewed catalog at `data/vendor_catalog.json` using the `{"vendors": [...]}` structure. Without it, the app runs with an empty vendor inventory.

Keep credentials in a local `.env` file or Streamlit secrets file; do not commit them.