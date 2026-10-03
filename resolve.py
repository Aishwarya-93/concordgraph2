"""Entity resolution: raw district names -> master IDs with confidence scores."""
import re, pandas as pd
from rapidfuzz import process, fuzz
from ingest import connect

def norm(s):
    s = re.sub(r"\b(district|dist)\b\.?", " ", str(s).lower()); s = re.sub(r"[^a-z ]", " ", s); return " ".join(s.split())

def _apply(con):
    con.execute("update facts set district_id=(select matched_id from resolution r where r.district_raw=facts.district_raw and r.status in ('auto','approved'))")

def main():
    con = connect(); dm = con.execute("select * from districts").df()
    ch = {}
    for _, r in dm.iterrows():
        for a in [r["name"]] + [x for x in str(r["aliases"]).split("|") if x]: ch[norm(a)] = r["id"]
    raws = con.execute("select distinct district_raw from facts").df().district_raw
    rows = []
    for raw in raws:
        m = process.extractOne(norm(raw), list(ch), scorer=fuzz.ratio); sc = round(m[1], 1)
        rows.append((raw, norm(raw), ch[m[0]], sc, "fuzzy-ratio (alias-aware)", "auto" if sc >= 90 else "review" if sc >= 70 else "unmatched"))
    res = pd.DataFrame(rows, columns=["district_raw", "normalized", "matched_id", "score", "method", "status"])
    res = res.merge(dm[["id", "name"]], left_on="matched_id", right_on="id").drop(columns="id").rename(columns={"name": "matched_name"})
    con.execute("drop table if exists resolution"); con.register("r_", res); con.execute("create table resolution as select * from r_")
    _apply(con); print(res.status.value_counts().to_dict()); con.close()

def decide(raw, action, new_id=None):
    """action: approve | reject | change (manual canonical id). Logged to review_log."""
    import datetime
    con = connect(); con.execute("create table if not exists review_log(ts varchar, district_raw varchar, action varchar, from_id varchar, to_id varchar)")
    old = con.execute("select matched_id from resolution where district_raw=?", [raw]).fetchone()[0]
    if action == "approve": con.execute("update resolution set status='approved' where district_raw=?", [raw]); new_id = old
    elif action == "change": con.execute("update resolution set matched_id=?, matched_name=(select name from districts where id=?), status='approved', method='manual', score=100 where district_raw=?", [new_id, new_id, raw])
    else: con.execute("update resolution set status='rejected' where district_raw=?", [raw]); new_id = None
    con.execute("update facts set district_id=NULL where district_raw=?", [raw]); _apply(con)
    con.execute("insert into review_log values (?,?,?,?,?)", [datetime.datetime.now().isoformat(timespec="seconds"), raw, action, old, new_id]); con.close()

def approve_all_review():
    con = connect(); con.execute("update resolution set status='approved' where status='review'"); _apply(con); con.close()

if __name__ == "__main__": main()
