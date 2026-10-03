"""FastAPI layer over existing modules (analytics / intents+nlq / provenance) and DuckDB. Serves the React build from frontend/dist."""
import threading, json, os, pandas as pd
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ingest, resolve, analytics as A, intents as I, provenance as P
if not os.path.exists(ingest.DB): ingest.main(); resolve.main()
app = FastAPI(title="ConcordGraph API"); LOCK = threading.RLock(); C = {}
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
def js(df): return json.loads(df.to_json(orient="records"))
def cached(k, fn):
    if k not in C: C[k] = fn()
    return C[k]
def _names(): return A.load()[1].name.tolist()

@app.get("/api/overview")
def overview():
    with LOCK:
        f, m = A.load(); return dict(districts=int(f.district_id.nunique()), schemes=int(f[f.allocated.notna()].scheme.nunique()), ministries=int(f.ministry.nunique()),
            alerts=len(cached("al", A.alerts)), convergence=len(cached("cv", A.convergence)), districts_list=m.name.tolist(), files=sorted(f.source_file.unique().tolist()))

@app.get("/api/map")
def map_(scheme: str = "All", metric: str = "spent"):
    with LOCK:
        f, m = A.load(); al = cached("al", A.alerts); cv = cached("cv", A.convergence)
        s = f[f.allocated.notna()]; s = s if scheme == "All" else s[s.scheme == scheme]
        g = s.groupby("district_id").agg(spent=("spent", "sum"), released=("released", "sum"), beneficiaries=("beneficiaries", "sum")); g["utilization"] = g.spent/g.released
        d = m.set_index("id").join(g).join(f[f.scheme == "Outcome"].set_index("district_id").value.rename("development_index"))
        d["anomaly_count"] = d.name.map(al.district.value_counts()).fillna(0); d["convergence_schemes"] = d.name.map(cv.set_index("name").n_schemes).fillna(0)
        d["value"] = d[metric].round(3); return js(d[["name", "lat", "lon", "value"]])

@app.get("/api/district/{name}")
def district(name: str):
    with LOCK:
        r, b, tr, out = A.profile(name); al = cached("al", A.alerts); cv = cached("cv", A.convergence); p, own = A.peers(name)
        c = cv[cv.name == name]
        return dict(name=name, population_lakh=float(r.population_lakh), development_index=out, schemes=js(b), trend=js(tr.reset_index()), alerts=js(al[al.district == name]), convergence=js(c) if len(c) else None, peers=js(p))

@app.get("/api/alerts")
def alerts():
    with LOCK: return js(cached("al", A.alerts))
@app.get("/api/convergence")
def convergence():
    with LOCK: return js(cached("cv", A.convergence))

@app.get("/api/compare")
def compare(names: str):
    with LOCK:
        al = cached("al", A.alerts); out = []
        for n in names.split(",")[:3]:
            r, b, tr, o = A.profile(n); out.append(dict(district=n, development_index=o, allocated=round(float(b.allocated.sum()), 1), released=round(float(b.released.sum()), 1), spent=round(float(b.spent.sum()), 1),
                utilization=round(float(b.spent.sum()/b.released.sum()), 2), beneficiaries=int(b.beneficiaries.sum()), alerts=int((al.district == n).sum())))
        return out

@app.get("/api/evidence")
def evidence(file: str, rows: str = ""):
    with LOCK:
        f, _ = A.load(); ok, stored, now = P.verify(file) if file != "facts" else (True, "", "")
        ids = [int(x) for x in rows.split(",") if x.strip().isdigit()]
        d = f[(f.source_file == file) & (f.source_row.isin(ids) if ids else True)].drop(columns=["district_id", "source"]).head(200)
        return dict(file=file, verified=ok, stored=stored, current=now, rows=js(d))
@app.post("/api/provenance/{action}")
def prov(action: str, file: str):
    with LOCK:
        {"tamper": P.tamper, "restore": P.restore}[action](file); return {"ok": True}

@app.get("/api/resolution")
def resolution():
    with LOCK:
        con = ingest.connect(True); r = con.execute("select * from resolution order by score").df()
        log = con.execute("select * from review_log").df() if "review_log" in [x[0] for x in con.execute("show tables").fetchall()] else pd.DataFrame(); con.close()
        return dict(rows=js(r), log=js(log))
class Decide(BaseModel): raw: str; action: str; new_name: str | None = None
@app.post("/api/resolution/decide")
def decide(b: Decide):
    with LOCK:
        nid = None
        if b.action == "change": f, m = A.load(); nid = m[m.name == b.new_name].id.iloc[0]
        resolve.decide(b.raw, b.action, nid); C.clear(); return {"ok": True}

@app.get("/api/quality")
def quality():
    with LOCK:
        con = ingest.connect(True); fa = con.execute("select * from facts").df(); rs = con.execute("select * from resolution").df(); con.close(); rows = []
        for s, d in fa.groupby("source"):
            rr = rs[rs.district_raw.isin(d.district_raw)]; rows.append({"dataset": s, "scheme": d.scheme.iloc[0], "ministry": d.ministry.iloc[0], "rows": len(d), "missing_values": int(d.drop(columns=["district_id"]).isna().sum().sum()),
                "duplicates": int(d.duplicated(["district_raw", "year"]).sum()), "auto_matched": int((rr.status == "auto").sum()), "needs_review": int((rr.status == "review").sum()), "unmatched": int(rr.status.isin(["unmatched", "rejected"]).sum())})
        return rows

class Ask(BaseModel): q: str; lang: str = "en"; ctx: dict | None = None
@app.post("/api/ask")
def ask(b: Ask):
    with LOCK:
        try: res = I.answer(b.q, b.ctx, b.lang, _names())
        except Exception as e: return dict(text=f"Could not run that question: {e}", ok=False, ctx=b.ctx)
        df = res["df"]; chart = None
        if df is not None and res["chart"]:
            k, x, y = res["chart"]
            if k == "line" and "district" in df: pv = df.pivot_table(index=x, columns="district", values=y)
            elif k == "cmp": pv = df.pivot_table(index="district", columns="scheme", values="spent_cr")
            else: pv = df.set_index(x)[[y]]
            pv.index = pv.index.astype(str); chart = dict(kind="line" if k == "line" else "bar", series=[str(c) for c in pv.columns], data=js(pv.reset_index().rename(columns={pv.index.name or "index": "x"})))
        return dict(ok=df is not None, text=res["text"], sql=res["sql"], sources=res["sources"][:80], kind=res["kind"], detected=res["lang"], chart=chart, columns=[] if df is None else [c for c in df.columns if c != "sources"],
                    rows=[] if df is None else js(df.drop(columns=["sources"], errors="ignore")), ctx=res["ctx"] if df is not None else b.ctx)

dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
if os.path.isdir(dist): app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
