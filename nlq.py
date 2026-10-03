"""Natural-language -> guarded SQL with provenance. Works offline via cache.json; uses Anthropic API if ANTHROPIC_API_KEY is set."""
import os, re, json, duckdb
from ingest import DB, H
CACHE = os.path.join(H, "cache.json")
SYSTEM = """You write DuckDB SQL only (no prose, no markdown). Question may be English/Hindi/Marathi.
Tables: facts(source,scheme,ministry,district_raw,district_id,year,allocated,released,spent,beneficiaries,indicator,value,source_file,source_row) amounts in Rs Cr;
districts(id,name,aliases,lat,lon,population_lakh,rural_share,tribal_share). scheme in ('MGNREGA','PMAY-G','JJM','Outcome').
Spending rows have allocated not null; Outcome rows hold the development index in `value` (2023).
Join facts f to districts d on d.id=f.district_id. ALWAYS include a column `sources` = list(f.source_file||':'||f.source_row) for aggregates (or f.source_file||':'||f.source_row for row-level). One SELECT only.
The user may write in English, Hindi (Devanagari) or Marathi. Always translate district names to the English spelling used in districts.name (e.g. नाशिक/नाशिक->Nashik, पुणे->Pune, मुंबई->Mumbai City, नागपूर->Nagpur) and match with d.name.
Use lower(d.name) like '%x%' if unsure of spelling. If the question cannot be answered from these tables, return: select 'Cannot answer from available data' as message"""
J = "from facts f join districts d on d.id=f.district_id"
SEED = {
 "top 5 districts by total spending across all schemes": f"select d.name, round(sum(f.spent),1) spent_cr, list(f.source_file||':'||f.source_row) sources {J} where f.allocated is not null group by 1 order by 2 desc limit 5",
 "which districts use less than 60% of released funds in any scheme?": f"select d.name, f.scheme, round(sum(f.spent)/sum(f.released),2) utilization, list(f.source_file||':'||f.source_row) sources {J} where f.allocated is not null group by 1,2 having sum(f.spent)/sum(f.released)<0.6 order by 3",
 "कौन से जिले में PMAY-G का सबसे ज्यादा आवंटन है?": f"select d.name, round(sum(f.allocated),1) allocated_cr, list(f.source_file||':'||f.source_row) sources {J} where f.scheme='PMAY-G' group by 1 order by 2 desc limit 5",
 "which districts have the lowest development index?": f"select d.name, f.value development_index, f.source_file||':'||f.source_row sources {J} where f.scheme='Outcome' order by 2 limit 5",
 "year-wise total jjm spending": f"select f.year, round(sum(f.spent),1) spent_cr, list(f.source_file||':'||f.source_row) sources {J} where f.scheme='JJM' group by 1 order by 1"}
BAN = re.compile(r"\b(drop|delete|insert|update|attach|detach|copy|create|alter|pragma|install|load|export|call|set|read_csv|read_parquet|read_json|glob)\b", re.I)

def _save(c):
    with open(CACHE, "w", encoding="utf-8") as fh: json.dump(c, fh, ensure_ascii=False, indent=1)

def _cache():
    try:
        with open(CACHE, encoding="utf-8") as fh: return json.load(fh)
    except Exception:
        _save(SEED); return dict(SEED)

def guard(sql):
    s = sql.strip().rstrip(";").strip()
    if ";" in s or not re.match(r"(?is)^(select|with)\b", s) or BAN.search(s): raise ValueError("Blocked: only a single read-only SELECT is allowed.")
    return s

MODEL = os.environ.get("CONCORD_MODEL", "claude-sonnet-4-6")

def _client():
    import anthropic; return anthropic.Anthropic()

def _llm(q, prev=None, err=None):
    msgs = [{"role": "user", "content": q}]
    if prev: msgs += [{"role": "assistant", "content": prev}, {"role": "user", "content": f"That SQL failed: {err}\nReturn corrected DuckDB SQL only."}]
    r = _client().messages.create(model=MODEL, max_tokens=700, system=SYSTEM, messages=msgs)
    return re.sub(r"```(sql)?", "", r.content[0].text).strip()

def _run(sql):
    sql = guard(sql); con = duckdb.connect(DB, read_only=True)
    try: return sql, con.execute(f"select * from ({sql}) limit 200").df()
    finally: con.close()

def explain(q, df):
    """2-sentence answer in the SAME language as the question (needs API key)."""
    try:
        r = _client().messages.create(model=MODEL, max_tokens=300, messages=[{"role": "user", "content":
            f"Question: {q}\nResult table (Rs Cr):\n{df.drop(columns=['sources'], errors='ignore').head(15).to_string()}\n"
            "Answer the question in 1-3 short sentences using ONLY this table, in the same language and script as the question. No speculation, no causal claims."}])
        return r.content[0].text.strip()
    except Exception: return ""

def ask(q, use_cache=True):
    """returns (sql, df, sources, message)"""
    c = _cache(); key = q.strip(); sql = (c.get(key) or c.get(key.lower())) if use_cache else None; fresh = False
    if not sql:
        if not os.environ.get("ANTHROPIC_API_KEY"): return None, None, None, "This question isn't cached. Paste your Anthropic API key in the sidebar to ask anything."
        sql = _llm(key); fresh = True
    err = None
    for attempt in range(2):
        try: sql, df = _run(sql); err = None; break
        except Exception as e:
            err = str(e)
            if not fresh or attempt == 1: break
            try: sql = _llm(key, sql, err)
            except Exception as e2: err = str(e2); break
    if err: return sql, None, None, f"Could not run query: {err}"
    if fresh and "message" not in df: c[key] = sql; _save(c)
    src = []
    if "sources" in df:
        for x in df["sources"]: src.extend([x] if isinstance(x, str) else list(x))
    return sql, df, sorted(set(map(str, src))), ""

def questions(): return list(_cache())
