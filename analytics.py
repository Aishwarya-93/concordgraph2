"""Explainable analytics: alerts (with reason + Rs at risk), overlap, gaps, peer districts. Associations only, never causal."""
import pandas as pd, numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from ingest import connect

def load():
    con = connect(True); f = con.execute("select * from facts where district_id is not null").df(); m = con.execute("select * from districts").df(); con.close(); return f, m

def _agg(f, m):
    s = f[f.allocated.notna()]
    g = s.groupby(["district_id", "scheme"]).agg(allocated=("allocated", "sum"), released=("released", "sum"), spent=("spent", "sum"),
        src=("source_file", "first"), rows=("source_row", lambda x: ",".join(map(str, sorted(x))))).reset_index()
    g["util"] = g.spent/g.released; g["rel"] = g.released/g.allocated
    return g.merge(m[["id", "name", "population_lakh"]], left_on="district_id", right_on="id")

def alerts():
    """Transparent rule-based alerts. Each row: type, observed, benchmark, why (calculation steps), suggestion, evidence rows."""
    f, m = load(); g = _agg(f, m); out = []; S = {"util": "Review pending works, implementation status and release-to-expenditure delays.", "rel": "Review release approvals and the timing of fund releases against allocation.",
        "out": "Compare with peer districts and check whether schemes target the needs behind this outcome.", "tmp": "Check what changed in the flagged year (project completions, delayed releases, reporting changes).", "per": "Review pending works over several years and implementation capacity."}
    def add(d, sch, typ, reason, risk, obs, bench, why, sug, src, rows): out.append(dict(district=d, scheme=sch, type=typ, reason=reason, rupees_cr_at_risk=round(risk, 1), observed=obs, benchmark=bench, why=why, suggestion=sug, source_file=src, source_rows=rows))
    for sch, d in g.groupby("scheme"):
        mu, mr = d.util.median(), d.rel.median()
        for _, r in d.iterrows():
            if r.util < mu-.15: add(r["name"], sch, "Potential under-utilization", f"{r['name']} spent {r.util:.0%} of released {sch} funds vs state median {mu:.0%}.", (mu-r.util)*r.released, r.util, mu,
                f"1. {sch} utilization = spent/released = {r.spent:.1f}/{r.released:.1f} = {r.util:.0%}\n2. State median = {mu:.0%}\n3. Difference = {(r.util-mu)*100:.0f} percentage points\n4. Released funds = Rs {r.released:.1f} Cr", S["util"], r.src, r.rows)
            if r.rel < mr-.15: add(r["name"], sch, "Funding anomaly (low release vs allocation)", f"{r['name']} received only {r.rel:.0%} of allocated {sch} funds vs state median {mr:.0%}.", (mr-r.rel)*r.allocated, r.rel, mr,
                f"1. Release ratio = released/allocated = {r.released:.1f}/{r.allocated:.1f} = {r.rel:.0%}\n2. State median = {mr:.0%}\n3. Difference = {(r.rel-mr)*100:.0f} pp\n4. Allocated = Rs {r.allocated:.1f} Cr", S["rel"], r.src, r.rows)
    y = f[f.allocated.notna()].groupby(["district_id", "scheme", "year"]).agg(sp=("spent", "sum"), rl=("released", "sum")).reset_index(); y["u"] = y.sp/y.rl
    y["med"] = y.groupby(["scheme", "year"]).u.transform("median"); nm = m.set_index("id")["name"]; rows = f.groupby(["district_id", "scheme"]).source_row.apply(lambda x: ",".join(map(str, sorted(x)))); fl = f.groupby(["district_id", "scheme"]).source_file.first()
    for (did, sch), t in y.groupby(["district_id", "scheme"]):
        t = t.sort_values("year"); low = t[t.u < t.med-.15]; dr = t.u.diff(); k = (did, sch)
        if len(low) >= 3: add(nm[did], sch, "Persistent underperformance", f"{nm[did]}: {sch} utilization was >15 pp below the state median in {len(low)} of {len(t)} years.", float(low.rl.sum()-low.sp.sum()), float(low.u.mean()), float(low.med.mean()),
            "1. Years flagged: " + ", ".join(f"{int(r.year)} ({r.u:.0%} vs {r.med:.0%})" for r in low.itertuples()), S["per"], fl[k], rows[k])
        if dr.min() <= -.15:
            j = dr.idxmin(); add(nm[did], sch, "Temporal anomaly (sudden drop)", f"{nm[did]}: {sch} utilization fell {abs(dr[j])*100:.0f} pp in {int(t.loc[j, 'year'])}.", float(t.loc[j, "rl"]*abs(dr[j])), float(t.loc[j, "u"]), float(t.loc[j, "u"]-dr[j]),
                "1. Utilization by year: " + ", ".join(f"{int(r.year)}={r.u:.0%}" for r in t.itertuples()), S["tmp"], fl[k], rows[k])
    tot = g.groupby("district_id").agg(spent=("spent", "sum")).join(m.set_index("id")[["name", "population_lakh"]]); oc = f[f.scheme == "Outcome"].set_index("district_id")
    tot["pc"] = tot.spent/tot.population_lakh; tot = tot.join(oc[["value", "source_file", "source_row"]]).dropna(); mdl = LinearRegression().fit(tot[["pc"]], tot.value); res = tot.value-mdl.predict(tot[["pc"]])
    for did, r in tot[res < -1.2*res.std()].iterrows():
        add(r["name"], "All schemes", "Outcome anomaly (high spend, relatively low outcome)", f"{r['name']} development index {r.value:.0f} is {abs(res[did]):.0f} pts below the level expected from its spend per lakh people (association only).", float(r.spent), float(r.value), float(mdl.predict(pd.DataFrame({'pc': [r.pc]}))[0]),
            f"1. Spend per lakh people = Rs {r.pc:.1f} Cr\n2. Fitted index at that spend = {r.value-res[did]:.0f}\n3. Actual index = {r.value:.0f} (synthetic outcome data: illustrative)", S["out"], r.source_file, str(int(r.source_row)))
    c = convergence(); q25 = c.development_index.quantile(.5) if len(c) else 0
    for r in c[c.development_index <= q25].itertuples():
        add(r.name, r.schemes, "Cross-scheme anomaly (many funded schemes, weak outcome)", f"{r.name}: {r.n_schemes} heavily funded schemes ({r.schemes}) but development index is {r.development_index:.0f}.", float(r.spent_cr), float(r.development_index), float(c.development_index.median()),
            f"1. Schemes in top-quartile funding per lakh people: {r.schemes}\n2. Combined spend = Rs {r.spent_cr:.1f} Cr\n3. Development index = {r.development_index:.0f} (convergence-set median {c.development_index.median():.0f})", "Treat as a potential convergence opportunity: review coordination across these schemes.", "facts", "see convergence tab")
    df = pd.DataFrame(out); return df.sort_values("rupees_cr_at_risk", ascending=False).reset_index(drop=True)

def convergence(min_schemes=2):
    f, m = load(); g = _per_lakh(f, m); g["high"] = g.groupby("scheme").pc.transform(lambda x: x > x.quantile(.75))
    h = g[g.high].groupby("name").agg(n_schemes=("scheme", "count"), schemes=("scheme", ", ".join), allocated_cr=("allocated", "sum"), released=("released", "sum"), spent_cr=("spent", "sum")).reset_index()
    nmap = m.set_index("id")["name"]; s = f[f.allocated.notna()]; ben = s.groupby(s.district_id.map(nmap)).beneficiaries.sum().rename("beneficiaries").rename_axis("name").reset_index()
    o = f[f.scheme == "Outcome"].assign(name=lambda x: x.district_id.map(nmap))[["name", "value"]].rename(columns={"value": "development_index"})
    h = h.merge(ben, on="name").merge(o, on="name"); h["utilization"] = (h.spent_cr/h.released).round(2); h["status"] = "Potential convergence opportunity (requires further investigation)"
    return h[h.n_schemes >= min_schemes].drop(columns="released").sort_values(["n_schemes", "development_index"], ascending=[False, True]).round(1).reset_index(drop=True)

def profile(name):
    f, m = load(); r = m[m["name"] == name].iloc[0]; s = f[(f.district_id == r.id) & f.allocated.notna()]
    b = s.groupby("scheme").agg(ministry=("ministry", "first"), allocated=("allocated", "sum"), released=("released", "sum"), spent=("spent", "sum"), beneficiaries=("beneficiaries", "sum")).reset_index()
    b["utilization"] = (b.spent/b.released).round(2); den = b.beneficiaries.where(b.beneficiaries > 0)
    b["spent_per_beneficiary_Rs"] = (b.spent*1e7/den).round(0); b["alloc_per_beneficiary_Rs"] = (b.allocated*1e7/den).round(0)
    t = s.groupby(["year", "scheme"]).agg(sp=("spent", "sum"), rl=("released", "sum")).reset_index(); t["u"] = t.sp/t.rl
    o = f[(f.district_id == r.id) & (f.scheme == "Outcome")].value
    return r, b.round(2), t.pivot(index="year", columns="scheme", values="u"), (float(o.iloc[0]) if len(o) else None)

def _per_lakh(f, m):
    g = _agg(f, m); g["pc"] = g.allocated/g.population_lakh; return g

def overlap():
    f, m = load(); g = _per_lakh(f, m); g["high"] = g.groupby("scheme").pc.transform(lambda x: x > x.quantile(.75))
    h = g[g.high].groupby("name").agg(n_schemes=("scheme", "count"), schemes=("scheme", ", ".join), total_alloc_cr=("allocated", "sum")).reset_index()
    o = f[f.scheme == "Outcome"].merge(m[["id", "name"]], left_on="district_id", right_on="id")[["name", "value"]].rename(columns={"value": "development_index"})
    return h[h.n_schemes >= 2].merge(o, on="name").sort_values("development_index").round(1)

def gaps():
    f, m = load(); g = _per_lakh(f, m).groupby("name").pc.sum().rename("alloc_cr_per_lakh").reset_index()
    o = f[f.scheme == "Outcome"].merge(m[["id", "name"]], left_on="district_id", right_on="id")[["name", "value"]].rename(columns={"value": "development_index"})
    d = g.merge(o, on="name"); return d[(d.development_index <= d.development_index.quantile(.25)) & (d.alloc_cr_per_lakh <= d.alloc_cr_per_lakh.median())].round(2)

def peers(district, k=5):
    f, m = load(); X = m[["population_lakh", "rural_share", "tribal_share"]]; Z = StandardScaler().fit_transform(X)
    o = f[f.scheme == "Outcome"].set_index("district_id").value; m = m.assign(outcome=m.id.map(o)).reset_index(drop=True)
    i = m.index[m.name == district][0]; idx = NearestNeighbors(n_neighbors=12).fit(Z).kneighbors(Z[[i]])[1][0][1:]
    p = m.loc[idx]; p = p[p.outcome > m.outcome[i]].head(k)
    s = f[f.allocated.notna()].groupby(["district_id", "scheme"]).spent.sum().unstack().div(m.set_index("id").population_lakh, axis=0).round(2)
    r = p.set_index("id")[["name", "outcome", "population_lakh", "rural_share", "tribal_share"]].join(s.add_suffix(" spent Cr/lakh"))
    return r.reset_index(drop=True), float(m.outcome[i])
