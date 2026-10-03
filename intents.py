"""Offline multilingual NLQ (English/Hindi/Marathi): normalise -> intent+slots -> safe SQL templates -> localized answer. No API needed."""
import re, pandas as pd
from rapidfuzz import fuzz
import nlq
J = "from facts f join districts d on d.id=f.district_id"
DEV = re.compile(r"[\u0900-\u097F]")
MR = ["मध्ये", "कोणत्या", "सर्वात", "जिल्ह्य", "आहे", "किती", "दाखवा", "करा", "चा ", "ची "]
HI = ["में", "किन", "सबसे", "कितना", "जिलों", "दिखाओ", "है", "क्या", "कौन", "का ", "की "]
SCH = {"JJM": ["jjm", "jal jeevan", "जल जीवन", "जेजेएम"], "PMAY-G": ["pmay", "pm awas", "आवास", "घरकुल", "पीएमएवाई"], "MGNREGA": ["mgnrega", "nrega", "मनरेगा", "नरेगा"]}
MET = [("per_ben", ["per beneficiary", "प्रति लाभार्थी", "प्रति लाभार्थ"]), ("util", ["utilization", "utilisation", "उपयोगिता", "उपयोग", "वापर", "विनियोग"]),
       ("alloc", ["allocation", "allocated", "budget", "आवंटन", "तरतूद", "बजट"]), ("ben", ["beneficiar", "लाभार्थी", "लाभार्थ"]),
       ("out", ["outcome", "development", "विकास", "निर्देशांक"]), ("spend", ["spending", "spent", "expenditure", "funding", "खर्च", "व्यय"])]
LOW = ["lowest", "least", "minimum", "bottom", "fewest", "सबसे कम", "सर्वात कमी", "सर्वात कम", "कमी", "कम "]
HIGH = ["highest", "most", "maximum", "top", "largest", "सबसे ज्यादा", "सबसे अधिक", "सबसे ज़्यादा", "सर्वात जास्त", "सर्वात अधिक", "सर्वाधिक", "अधिक", "जास्त", "ज्यादा"]
CMP = ["compare", "comparison", " vs ", "versus", "तुलना", "बनाम"]; TRD = ["over time", "trend", "year-wise", "yearly", "साल", "वर्ष", "कालांतराने", "दरवर्षी", "ट्रेंड", "प्रवृत्ती", "प्रवृत्ति"]
CNV = ["converge", "multiple schemes", "same districts", "overlap", "एकाधिक", "अभिसरण", "अनेक योजना", "एकापेक्षा", "कई योजना", "एक से अधिक"]
WHY = ["why", "क्यों", "कारण", "कशामुळे", "का कमी"]; PRON = ["it", "them", "that", "इसकी", "इसे", "त्याची", "त्याला"]
DD = {"नाशिक": "Nashik", "नासिक": "Nashik", "पुणे": "Pune", "नागपूर": "Nagpur", "नागपुर": "Nagpur", "ठाणे": "Thane", "औरंगाबाद": "Aurangabad", "कोल्हापूर": "Kolhapur", "कोल्हापुर": "Kolhapur",
      "सोलापूर": "Solapur", "सोलापुर": "Solapur", "जळगाव": "Jalgaon", "जलगांव": "Jalgaon", "अहमदनगर": "Ahmednagar", "बीड": "Beed", "लातूर": "Latur", "नांदेड": "Nanded", "अकोला": "Akola", "अमरावती": "Amravati",
      "धुळे": "Dhule", "सातारा": "Satara", "सांगली": "Sangli", "रायगड": "Raigad", "पालघर": "Palghar", "यवतमाळ": "Yavatmal", "वर्धा": "Wardha", "चंद्रपूर": "Chandrapur", "चंद्रपुर": "Chandrapur", "गडचिरोली": "Gadchiroli",
      "जालना": "Jalna", "परभणी": "Parbhani", "हिंगोली": "Hingoli", "वाशिम": "Washim", "भंडारा": "Bhandara", "गोंदिया": "Gondia", "बुलढाणा": "Buldhana", "उस्मानाबाद": "Osmanabad", "नंदुरबार": "Nandurbar", "रत्नागिरी": "Ratnagiri", "सिंधुदुर्ग": "Sindhudurg", "मुंबई": "Mumbai City"}
RDD = {}; [RDD.setdefault(v, k) for k, v in DD.items()]
MN = {"spend": ("spending", "खर्च", "खर्च"), "util": ("utilization", "उपयोगिता", "वापर"), "alloc": ("allocation", "आवंटन", "तरतूद"), "ben": ("beneficiaries", "लाभार्थी", "लाभार्थी"),
      "per_ben": ("spending per beneficiary", "प्रति लाभार्थी खर्च", "प्रति लाभार्थी खर्च"), "out": ("development index", "विकास सूचकांक", "विकास निर्देशांक")}
LI = {"en": 0, "hi": 1, "mr": 2}
HELP = {"en": "I couldn't map that to a known question type. Try: lowest/highest spending, utilization, allocation, beneficiaries or spending per beneficiary (optionally for JJM/PMAY-G/MGNREGA), 'Compare Nashik and Pune', 'trend over years', 'convergence', or 'Why is Nashik low?'.",
        "hi": "मैं यह प्रश्न समझ नहीं पाया। उदाहरण: 'किन जिलों में JJM का खर्च सबसे कम है?', 'नाशिक और पुणे की तुलना करें', 'JJM का साल-दर-साल रुझान', 'अभिसरण वाले जिले'।",
        "mr": "हा प्रश्न समजला नाही. उदाहरण: 'कोणत्या जिल्ह्यांमध्ये JJM चा खर्च सर्वात कमी आहे?', 'नाशिक आणि पुणे यांची तुलना करा', 'JJM चा वर्षानुसार कल', 'अभिसरण असलेले जिल्हे'."}

def lang(q):
    if not DEV.search(q): return "en"
    return "mr" if sum(w in q for w in MR) > sum(w in q for w in HI) else "hi"

def _any(q, ws): return [w for w in ws if w in q]
def _districts(q, names):
    hits = []
    for k, v in DD.items():
        if k in q: hits.append((q.find(k), v))
    ql = q.lower()
    for n in names:
        if n.lower() in ql: hits.append((ql.find(n.lower()), n))
    toks = [(m.start(), m.group()) for m in re.finditer(r"[a-z]{4,}", ql)]
    for n in names:
        if " " in n or any(p[1] == n for p in hits): continue
        for pos, t in toks:
            if fuzz.ratio(t, n.lower()) >= 84: hits.append((pos, n))
    seen = []; [seen.append(n) for _, n in sorted(hits) if n not in seen]; return seen

def parse(q, ctx, names):
    ql = " " + q.lower().strip() + " "
    sch = next((s for s, ws in SCH.items() if _any(ql, ws)), None)
    mh = [k for k, ws in MET if _any(ql, ws)]; dis = _districts(q, names)
    lo, hi = _any(ql, LOW), _any(ql, HIGH); dirn = ("low" if min([ql.find(w) for w in lo] or [9e9]) < min([ql.find(w) for w in hi] or [9e9]) else "high") if (lo or hi) else None
    kind = "why" if _any(ql, WHY) else "compare" if _any(ql, CMP) else "trend" if _any(ql, TRD) else "conv" if _any(ql, CNV) else \
           "conv" if ("out" in mh and {"alloc", "spend"} & set(mh)) else "lookup" if dis else "rank" if (mh or dirn or sch) else None
    sch0 = sch; follow = len(q.split()) <= 7 or any(re.search(rf"\b{p}\b", ql) for p in PRON if p.isascii())
    n = next((int(x) for x in re.findall(r"\b(\d{1,2})\b", q)), 5)
    metric = next((k for k in mh if k != "out" or len(mh) == 1), None)
    if follow and ctx:
        sch = sch or ctx.get("scheme"); metric = metric or (None if kind == "why" else ctx.get("metric")); dirn = dirn or ctx.get("dirn")
        if sch0 and (kind is None or (kind == "rank" and not mh and not lo and not hi)): kind = ctx.get("kind") or kind
        if kind == "compare" and len(dis) == 1 and ctx.get("districts"): dis = [ctx["districts"][-1]] + [d for d in dis if d != ctx["districts"][-1]]
        elif not dis and kind in ("why", "compare", "lookup", "trend") and ctx.get("districts"): dis = ctx["districts"]
        if kind is None and sch: kind = ctx.get("kind")
    if kind == "why" and not metric: metric = "util"
    if kind in ("rank", "lookup", "trend") and not metric: metric = "spend"
    return dict(scheme=sch, metric=metric, districts=dis, dirn=dirn or "high", kind=kind, n=min(n, 36) if n != 5 or "5" in q else 5)

def _sql(p):
    m = p["metric"]; sc = p["scheme"]; src = "list(f.source_file||':'||f.source_row) as sources"
    ex = {"spend": ("sum(f.spent)", 1), "util": ("sum(f.spent)/nullif(sum(f.released),0)", 3), "alloc": ("sum(f.allocated)", 1), "ben": ("sum(f.beneficiaries)", 0), "per_ben": ("sum(f.spent)*1e7/nullif(sum(f.beneficiaries),0)", 0), "out": ("avg(f.value)", 1)}
    e, r = ex.get(m, ex["spend"]); w = "f.scheme='Outcome'" if m == "out" else "f.allocated is not null" + (f" and f.scheme='{sc}'" if sc else "")
    dl = ",".join("'" + d.replace("'", "") + "'" for d in p["districts"])
    if p["kind"] == "rank": return f"select d.name as district, round({e},{r}) as value, {src} {J} where {w} group by 1 order by 2 {'asc' if p['dirn']=='low' else 'desc'} nulls last limit {p['n']}"
    if p["kind"] == "lookup": return f"select d.name as district, round({e},{r}) as value, {src} {J} where {w} and d.name in ({dl}) group by 1 order by 1"
    if p["kind"] == "trend":
        w2 = w + (f" and d.name in ({dl})" if dl else ""); return f"select f.year, {'d.name as district,' if dl else ''} round({e},{r}) as value, {src} {J} where {w2} group by {'1,2' if dl else '1'} order by 1"
    if p["kind"] == "compare":
        w2 = "f.allocated is not null" + (f" and f.scheme='{sc}'" if sc else "") + f" and d.name in ({dl})"
        return (f"select d.name as district, f.scheme, round(sum(f.allocated),1) allocated_cr, round(sum(f.released),1) released_cr, round(sum(f.spent),1) spent_cr, round(sum(f.spent)/nullif(sum(f.released),0),3) utilization, "
                f"sum(f.beneficiaries) beneficiaries, round(sum(f.spent)*1e7/nullif(sum(f.beneficiaries),0)) spent_per_beneficiary_rs, {src} {J} where {w2} group by 1,2 order by 1,2")

def _fmt(m, v):
    if v is None or pd.isna(v): return "n/a"
    return f"{v:.0%}" if m == "util" else f"₹{v:,.0f}" if m == "per_ben" else f"{v:,.0f}" if m == "ben" else f"{v:,.1f}" + ("" if m == "out" else " Cr")

def answer(q, ctx, lg, names):
    """returns dict(text, df, sql, sources, kind, ctx, lang, chart)"""
    import analytics as A
    p = parse(q, ctx or {}, names); i = LI[lg]; k = p["kind"]; res = dict(lang=lang(q), kind=k, text="", df=None, sql=None, sources=[], chart=None, ctx=ctx)
    if not k: res["text"] = HELP[lg]; return res
    mw = MN.get(p["metric"], MN["spend"])[i]; sch = p["scheme"] or ""; loc = lambda d: RDD.get(d, d) if lg != "en" else d
    if k == "conv":
        df = A.convergence(); res.update(df=df, sql="computed by analytics.convergence() over facts + districts", chart=("bar", "name", "allocated_cr"))
        nm = ", ".join(df.name.head(5)); res["text"] = {"en": f"{len(df)} districts show potential scheme convergence (2+ heavily funded schemes): {nm}. This is an observed pattern that requires further investigation.",
            "hi": f"{len(df)} जिलों में संभावित योजना-अभिसरण दिखता है (2+ अधिक वित्तपोषित योजनाएँ): {', '.join(loc(x) for x in df.name.head(5))}। यह केवल एक देखा गया पैटर्न है, इसकी आगे जाँच आवश्यक है।",
            "mr": f"{len(df)} जिल्ह्यांमध्ये संभाव्य योजना-अभिसरण दिसते (2+ जास्त निधी असलेल्या योजना): {', '.join(loc(x) for x in df.name.head(5))}. हा केवळ निरीक्षित नमुना आहे, पुढील तपासणी आवश्यक आहे."}[lg]
    elif k == "why":
        if not p["districts"]: res["text"] = HELP[lg]; return res
        d = p["districts"][-1]; p2 = dict(p, kind="rank", n=36, dirn="low"); sql, all_ = nlq._run(_sql(p2)); med = all_.value.median(); r = all_[all_.district == d]
        if r.empty: res["text"] = HELP[lg]; return res
        v = float(r.value.iloc[0]); df = pd.DataFrame([dict(district=d, scheme=sch or "All", metric=mw, value=round(v, 3), state_median=round(float(med), 3), difference=round(v-float(med), 3), sources=r.sources.iloc[0])])
        res.update(df=df, sql=sql, chart=("bar", "district", "value")); dif = _fmt(p["metric"], v) + " vs " + _fmt(p["metric"], med)
        res["text"] = {"en": f"{d}: {sch} {mw} is {dif} (state median). Differences from the benchmark are patterns to investigate, not proof of a cause.", "hi": f"{loc(d)}: {sch} {mw} {dif} (राज्य माध्यिका) है। बेंचमार्क से अंतर जाँच योग्य पैटर्न है, कारण का प्रमाण नहीं।",
            "mr": f"{loc(d)}: {sch} {mw} {dif} (राज्य मध्यक) आहे. बेंचमार्कमधील फरक तपासण्याजोगा नमुना आहे, कारणाचा पुरावा नाही."}[lg]
    else:
        if k == "compare" and len(p["districts"]) < 2: res["text"] = HELP[lg]; return res
        sql = _sql(p); sql, df = nlq._run(sql); res.update(df=df, sql=sql)
        if df.empty: res["text"] = HELP[lg]; return res
        if k == "rank":
            dw = {"low": ("Lowest", "सबसे कम", "सर्वात कमी"), "high": ("Highest", "सबसे अधिक", "सर्वात जास्त")}[p["dirn"]][i]
            res["text"] = f"{sch} {mw} — {dw}: " + ", ".join(f"{loc(r.district)} ({_fmt(p['metric'], r.value)})" for r in df.head(3).itertuples()); res["chart"] = ("bar", "district", "value")
        elif k == "lookup":
            r = df.iloc[0]; t = {"en": "{d}: {s} {m} = {v}", "hi": "{d} जिले में {s} के लिए {m}: {v} है।", "mr": "{d} जिल्ह्यात {s} साठी {m}: {v} आहे."}[lg]
            res["text"] = " | ".join(t.format(d=loc(r.district), s=sch or "", m=mw, v=_fmt(p["metric"], r.value)) for r in df.itertuples()); res["chart"] = ("bar", "district", "value")
        elif k == "trend":
            res["text"] = {"en": f"{sch} {mw} by year: ", "hi": f"{sch} {mw} वर्षवार: ", "mr": f"{sch} {mw} वर्षानुसार: "}[lg] + " → ".join(f"{r.year}: {_fmt(p['metric'], r.value)}" for r in df.groupby("year").value.mean().reset_index().itertuples()); res["chart"] = ("line", "year", "value")
        else:
            res["text"] = {"en": "Comparison of ", "hi": "तुलना: ", "mr": "तुलना: "}[lg] + " / ".join(loc(d) for d in p["districts"]) + {"en": " (see table).", "hi": " (तालिका देखें)।", "mr": " (तक्ता पहा)."}[lg]; res["chart"] = ("cmp", "district", "spent_cr")
    s = []
    if df is not None and "sources" in df:
        for x in df["sources"]: s.extend([x] if isinstance(x, str) else list(x))
    res["sources"] = sorted(set(map(str, s))); res["ctx"] = dict(scheme=p["scheme"], metric=p["metric"], districts=p["districts"] or (ctx or {}).get("districts", []), dirn=p["dirn"], kind=k)
    return res
