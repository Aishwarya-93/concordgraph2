# ConcordGraph (PS-03) — React + TypeScript + FastAPI + DuckDB
## Run (only Python needed; the React app is pre-built in frontend/dist)
```
pip install -r requirements.txt
uvicorn api:app --port 8000
```
Open http://localhost:8000  (first start generates synthetic data + the DuckDB file).
## Develop the frontend (needs Node 18+)
```
cd frontend && npm install && npm run dev      # http://localhost:5173, proxies /api to :8000
npm run build                                   # refresh frontend/dist
```
## Architecture
React/TS (Map, Graph, Ask EN/HI/MR, Alerts, Review) -> FastAPI (`api.py`) -> analytics.py | intents.py+nlq.py | provenance.py -> DuckDB.
`app.py` (Streamlit) is the older UI and still works: `streamlit run app.py`.
## Notes
- NLQ works offline (rule-based EN/HI/MR); no API key needed. The map needs internet for OpenStreetMap tiles; voice input needs Chrome/Edge.
- If upgrading: delete `data/raw`, `concord.duckdb`, `cache.json`.
- DEMO DATA IS SYNTHETIC; findings are patterns to investigate, not causal claims.
