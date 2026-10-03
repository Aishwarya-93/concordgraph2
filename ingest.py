"""Load raw CSVs -> unified `facts` table in DuckDB. To use REAL data: drop CSVs in data/raw and edit MAP."""
import duckdb, pandas as pd, os, re
H = os.path.dirname(os.path.abspath(__file__)); DB = os.path.join(H, "concord.duckdb"); RAW = os.path.join(H, "data", "raw")
def connect(read_only=False): return duckdb.connect(DB, read_only=read_only)
# file -> (scheme, ministry, {raw column: unified column})
MAP = {"mgnrega.csv": ("MGNREGA", "Rural Development", dict(district_name="district_raw", fin_year="year", sanctioned_cr="allocated", released_cr="released", expenditure_cr="spent", households="beneficiaries")),
       "pmayg.csv": ("PMAY-G", "Rural Development (Housing)", dict(District="district_raw", Year="year", Allocated="allocated", Released="released", Spent="spent", Houses="beneficiaries")),
       "jjm.csv": ("JJM", "Jal Shakti", dict(dist="district_raw", fy="year", alloc="allocated", rel="released", exp="spent", connections="beneficiaries"))}
COLS = ["source", "scheme", "ministry", "district_raw", "district_id", "year", "allocated", "released", "spent", "beneficiaries", "indicator", "value", "source_file", "source_row"]

def main():
    if not os.path.exists(os.path.join(RAW, "outcome.csv")):
        import sys; sys.path.insert(0, os.path.join(H, "data")); import synth; synth.main()
    parts = []
    for fn, (scheme, ministry, cm) in MAP.items():
        d = pd.read_csv(os.path.join(RAW, fn)).rename(columns=cm)[list(cm.values())]
        d["year"] = d["year"].astype(str).str.extract(r"(\d{4})")[0].astype(int)
        d["source"], d["scheme"], d["ministry"], d["source_file"], d["source_row"] = fn, scheme, ministry, fn, range(2, len(d)+2)
        parts.append(d)
    o = pd.read_csv(os.path.join(RAW, "outcome.csv")).rename(columns={"district": "district_raw"})
    o["source"], o["scheme"], o["ministry"], o["source_file"], o["source_row"] = "outcome.csv", "Outcome", "Health & Planning", "outcome.csv", range(2, len(o)+2)
    parts.append(o)
    f = pd.concat(parts, ignore_index=True); f["district_id"] = None
    f = f.reindex(columns=COLS)
    dm = pd.read_csv(os.path.join(H, "data", "districts_master.csv")).fillna("")
    con = connect()
    for t in ("facts", "districts", "resolution", "snapshots"): con.execute(f"drop table if exists {t}")
    con.register("f_", f); con.register("dm_", dm)
    con.execute("create table facts as select * from f_"); con.execute("alter table facts alter district_id type varchar"); con.execute("create table districts as select * from dm_")
    con.close()
    import provenance; provenance.snapshot()
    print(f"facts: {len(f)} rows, {f.source.nunique()} sources")

if __name__ == "__main__": main()
