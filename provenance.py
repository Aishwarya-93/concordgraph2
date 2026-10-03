"""Tamper-evident provenance: SHA-256 Merkle root per source file, verify, plus tamper/restore demo helpers."""
import hashlib, os, glob, shutil, sys
import pandas as pd
from ingest import connect, RAW

def _h(x): return hashlib.sha256(x.encode()).hexdigest()
def merkle_root(rows):
    lv = [_h(r) for r in rows] or [_h("")]
    while len(lv) > 1:
        if len(lv) % 2: lv.append(lv[-1])
        lv = [_h(lv[i]+lv[i+1]) for i in range(0, len(lv), 2)]
    return lv[0]
def _root(fn): return merkle_root(open(os.path.join(RAW, fn), encoding="utf-8").read().splitlines())

def snapshot():
    rows = [(os.path.basename(p), _root(os.path.basename(p)), len(open(p, encoding="utf-8").read().splitlines())) for p in sorted(glob.glob(os.path.join(RAW, "*.csv")))]
    df = pd.DataFrame(rows, columns=["file", "root", "n_lines"]); con = connect()
    con.execute("drop table if exists snapshots"); con.register("s_", df); con.execute("create table snapshots as select * from s_"); con.close()

def verify(fn):
    con = connect(True); r = con.execute("select root from snapshots where file=?", [fn]).fetchone(); con.close()
    now = _root(fn); return (r is not None and r[0] == now), (r[0] if r else None), now

def tamper(fn, line=5):
    p = os.path.join(RAW, fn); shutil.copy(p, p+".bak"); L = open(p, encoding="utf-8").read().splitlines(); c = L[line-1].split(",")
    c[-2 if fn != "outcome.csv" else -1] = str(round(float(c[-2 if fn != "outcome.csv" else -1])+1, 2)); L[line-1] = ",".join(c)
    open(p, "w", encoding="utf-8", newline="").write("\n".join(L)+"\n")
def restore(fn):
    p = os.path.join(RAW, fn)
    if os.path.exists(p+".bak"): shutil.move(p+".bak", p)

if __name__ == "__main__":
    cmd, fn = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "pmayg.csv")
    {"tamper": tamper, "restore": restore}.get(cmd, lambda f: print(verify(f)))(fn) if cmd != "verify" else print(verify(fn))
