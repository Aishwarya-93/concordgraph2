import os, streamlit as st, pandas as pd, pydeck as pdk
import ingest, resolve, analytics as A, nlq, intents as I, provenance as P
st.set_page_config(page_title="ConcordGraph", layout="wide")
if not os.path.exists(ingest.DB): ingest.main(); resolve.main()
f, m = A.load(); names = m.name.tolist(); nmap = m.set_index("id").name
SS = st.session_state; SS.setdefault("hist", []); SS.setdefault("ctx", None); SS.setdefault("sel", names[0])
al = A.alerts(); cv = A.convergence()
PAGES = ["Overview", "Governance Map", "Scheme Graph", "Ask ConcordGraph", "Intelligence / Alerts", "Scheme Convergence", "Compare Districts", "Entity Resolution", "Data Quality", "Evidence / Provenance"]
page = st.sidebar.radio("ConcordGraph", PAGES); st.sidebar.caption("Demo data is SYNTHETIC. Findings are associations / patterns to investigate, not causal claims.")

def rows_for(file, rs):
    if file == "facts" or not rs or "see" in str(rs): return pd.DataFrame()
    ids = [int(x) for x in str(rs).split(",") if x.strip().isdigit()]
    return f[(f.source_file == file) & f.source_row.isin(ids)].drop(columns=["district_id", "source"])
def evidence(file, rs):
    if file == "facts": st.caption("Evidence: see Scheme Convergence table (derived from facts)."); return
    ok, stored, now = P.verify(file); (st.success if ok else st.error)(("✓ Source verified" if ok else "✗ Source CHANGED since snapshot") + f" — {file} root {now[:12]}…")
    with st.expander("View source records"): st.dataframe(rows_for(file, rs))
def chart(df, spec):
    if df is None or not spec or df.empty: return
    k, x, y = spec
    try:
        if k == "bar": st.bar_chart(df.set_index(x)[y])
        elif k == "line": st.line_chart(df.pivot_table(index=x, columns="district", values=y) if "district" in df else df.groupby(x)[y].mean())
        elif k == "cmp": st.bar_chart(df.pivot_table(index="district", columns="scheme", values="spent_cr"))
    except Exception: pass

if page == "Overview":
    st.title("ConcordGraph")
    st.markdown("**A unified, explainable and traceable relationship layer across fragmented government programmes** — finds cross-scheme gaps, anomalies and convergence opportunities, and lets you investigate them in English, हिन्दी and मराठी.")
    c = st.columns(5); c[0].metric("Districts", f.district_id.nunique()); c[1].metric("Schemes", f[f.allocated.notna()].scheme.nunique()); c[2].metric("Ministries", f.ministry.nunique()); c[3].metric("Alerts", len(al)); c[4].metric("Convergence districts", len(cv))
    st.info("Pipeline: heterogeneous CSVs → entity resolution (with human review) → unified DuckDB layer → analytics → recommendations → multilingual NLQ → evidence & integrity verification.")
    st.warning("All data here is synthetic/demo. The outcome index is generated independently of spending (tribal share, urbanisation, planted effects), so any relationship shown is illustrative.")

elif page == "Governance Map":
    c1, c2 = st.columns(2); sch = c1.selectbox("Scheme", ["All"] + sorted(f[f.allocated.notna()].scheme.unique()))
    met = c2.selectbox("Metric", ["spent", "utilization", "beneficiaries", "development_index", "anomaly_count", "convergence_schemes"])
    s = f[f.allocated.notna()]; s = s if sch == "All" else s[s.scheme == sch]
    g = s.groupby("district_id").agg(spent=("spent", "sum"), released=("released", "sum"), beneficiaries=("beneficiaries", "sum")); g["utilization"] = (g.spent/g.released).round(2); g["spent"] = g.spent.round(1)
    d = m.set_index("id").join(g).join(f[f.scheme == "Outcome"].set_index("district_id").value.rename("development_index"))
    d["anomaly_count"] = d.name.map(al.district.value_counts()).fillna(0); d["convergence_schemes"] = d.name.map(cv.set_index("name").n_schemes).fillna(0); d = d.reset_index()
    v = d[met]; t = ((v-v.min())/(v.max()-v.min()+1e-9)).fillna(0); d["val"] = v.round(2); d["color"] = [[int(230*(1-x)), int(60+150*x), 90, 190] for x in t]; d["radius"] = 9000+30000*t
    lay = pdk.Layer("ScatterplotLayer", d, id="d", get_position="[lon, lat]", get_fill_color="color", get_radius="radius", pickable=True)
    deck = pdk.Deck(layers=[lay], initial_view_state=pdk.ViewState(latitude=19.0, longitude=76.5, zoom=5.2), tooltip={"text": "{name}\n" + met + ": {val}"})
    try:
        ev = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key="map")
        o = ev.selection.get("objects", {}).get("d", []) if ev and ev.selection else []
        if o: SS.sel = o[0]["name"]
    except Exception: st.pydeck_chart(deck)
    st.caption(f"Legend: green = higher {met}, red = lower (size scales too). Click a district or pick below.")
    SS.sel = st.selectbox("District profile", names, index=names.index(SS.sel)); r, b, tr, out = A.profile(SS.sel)
    st.subheader(f"{SS.sel} — district intelligence profile"); c = st.columns(6)
    for col, (lbl, val) in zip(c, [("Development index (syn.)", out), ("Population (lakh)", r.population_lakh), ("Allocated Cr", b.allocated.sum()), ("Released Cr", b.released.sum()), ("Spent Cr", b.spent.sum()), ("Beneficiaries", int(b.beneficiaries.sum()))]): col.metric(lbl, f"{val:,.1f}" if isinstance(val, float) else val)
    c = st.columns(2); c[0].markdown("**Scheme breakdown**"); c[0].dataframe(b); c[1].markdown("**Utilization trend**"); c[1].line_chart(tr)
    da = al[al.district == SS.sel]; st.markdown(f"**Alerts ({len(da)})**"); 
    if len(da): st.dataframe(da[["type", "scheme", "reason", "rupees_cr_at_risk"]])
    else: st.caption("No alerts.")
    if SS.sel in set(cv.name): st.success("Potential convergence opportunity: " + cv[cv.name == SS.sel].schemes.iloc[0])
    with st.expander("Peer comparison (association only)"):
        p, own = A.peers(SS.sel)
        if len(p): st.dataframe(p)
        else: st.write("No better-performing peers.")
    with st.expander("Evidence"): st.dataframe(f[f.district_id == m[m.name == SS.sel].id.iloc[0]].drop(columns=["district_id", "source"]))

elif page == "Scheme Graph":
    sel = st.selectbox("District", names, index=names.index(SS.sel)); SS.sel = sel; r, b, tr, out = A.profile(sel)
    dot = ["digraph G {rankdir=LR; node [shape=box, style=rounded, fontsize=11];"]
    for x in b.itertuples():
        mn = x.ministry.replace('"', ''); dot += [f'"{mn}" -> "{x.scheme}"; "{x.scheme}" -> "{sel}" [label="spent {x.spent:.0f} Cr\\n{x.utilization:.0%} util"];', f'"{x.scheme}" [style="rounded,filled", fillcolor="#dbeafe"];']
    dot += [f'"{sel}" -> "Beneficiaries {int(b.beneficiaries.sum()):,}"; "{sel}" -> "Development index {out}" [style=dashed]; "{sel}" [style="filled", fillcolor="#fde68a"];}}']
    st.graphviz_chart("\n".join(dot)); st.caption("Ministry → Scheme → District → Beneficiaries / Outcome. Built from the unified facts table; edge labels are computed values.")
    st.dataframe(b)

elif page == "Ask ConcordGraph":
    lg = {"English": "en", "हिन्दी": "hi", "मराठी": "mr"}[st.radio("Answer language", ["English", "हिन्दी", "मराठी"], horizontal=True)]
    st.caption("Works offline — no API key needed. Ask in English, Hindi or Marathi; follow-ups like 'Compare it with Pune' or 'What about PMAY-G?' use conversation context.")
    ex = {"en": ["Which districts have the lowest JJM utilization?", "Compare Nashik and Pune", "Which districts have high allocation but low outcomes?"], "hi": ["किन जिलों में JJM का उपयोग सबसे कम है?", "नाशिक जिले में JJM का उपयोग कितना है?"], "mr": ["कोणत्या जिल्ह्यांमध्ये JJM चा वापर सर्वात कमी आहे?", "नाशिक आणि पुणे यांची तुलना करा"]}[lg]
    c = st.columns(len(ex)); clicked = next((e for col, e in zip(c, ex) if col.button(e)), None)
    q = st.chat_input("Ask a question…") or clicked
    if st.button("Clear conversation"): SS.hist, SS.ctx = [], None; st.rerun()
    if q:
        try: res = I.answer(q, SS.ctx, lg, names)
        except Exception as e: res = dict(text=f"Could not run that question: {e}", df=None, sql=None, sources=[], chart=None, ctx=SS.ctx, kind=None, lang=lg)
        if res["df"] is None and res["kind"] is None and os.environ.get("ANTHROPIC_API_KEY"):
            sql, df, src, msg = nlq.ask(q); res.update(df=df, sql=sql, sources=src or [], text=msg or nlq.explain(q, df))
        if res["df"] is not None: SS.ctx = res["ctx"]
        SS.hist.append((q, res))
    for q, res in SS.hist[-4:][::-1]:
        with st.chat_message("user"): st.write(q)
        with st.chat_message("assistant"):
            if res["df"] is not None: st.success(res["text"])
            else: st.warning(res["text"])
            if res["df"] is not None:
                chart(res["df"], res["chart"]); st.dataframe(res["df"].drop(columns=["sources"], errors="ignore"))
                with st.expander("Evidence & SQL"): st.code(res["sql"] or "", "sql"); st.write(f"Detected language: {res['lang']} · intent: {res['kind']}"); st.write(res["sources"][:60])

elif page == "Intelligence / Alerts":
    ty = st.multiselect("Alert type", sorted(al.type.unique()), default=sorted(al.type.unique())); v = al[al.type.isin(ty)].reset_index(drop=True)
    st.dataframe(v[["district", "scheme", "type", "reason", "rupees_cr_at_risk"]]); i = st.number_input("Alert #", 0, max(len(v)-1, 0), 0); a = v.iloc[i]
    st.subheader(f"{a.type}: {a.district}"); c = st.columns(3); c[0].metric("Observed", f"{a.observed:.2f}"); c[1].metric("Benchmark", f"{a.benchmark:.2f}"); c[2].metric("Rs Cr at risk", a.rupees_cr_at_risk)
    with st.expander("❓ Why am I seeing this?", expanded=True): st.text(a.why)
    st.markdown(f"**Finding:** {a.reason}\n\n**Recommendation (for investigation):** {a.suggestion}\n\n**Evidence type:** rule-based comparison against peer/state benchmark — an observed pattern; it does not show misuse or cause.")
    evidence(a.source_file, a.source_rows)

elif page == "Scheme Convergence":
    st.write("Districts where 2+ schemes (across ministries) are in the top quartile of allocation per lakh people. A **potential convergence opportunity**, not evidence that programmes are or aren't coordinated.")
    st.dataframe(cv.drop(columns="status")); st.bar_chart(cv.set_index("name")[["allocated_cr", "spent_cr"]])
    st.caption("Limitation: the data has no beneficiary IDs, so beneficiary-level overlap cannot be measured; overlap is inferred from same district + funding intensity.")

elif page == "Compare Districts":
    sel = st.multiselect("Pick 2–3 districts", names, default=["Nashik", "Pune"], max_selections=3)
    if len(sel) >= 2:
        rows = []
        for n in sel:
            r, b, tr, out = A.profile(n); rows.append(dict(district=n, development_index=out, allocated=b.allocated.sum(), released=b.released.sum(), spent=b.spent.sum(), utilization=round(b.spent.sum()/b.released.sum(), 2), beneficiaries=int(b.beneficiaries.sum()), alerts=int((al.district == n).sum())))
        st.dataframe(pd.DataFrame(rows).set_index("district")); st.bar_chart(pd.concat({n: A.profile(n)[1].set_index("scheme").spent for n in sel}, axis=1)); st.line_chart(pd.concat({n: A.profile(n)[2].mean(axis=1) for n in sel}, axis=1))
        st.caption("Side-by-side facts only — no best/worst ranking implied.")

elif page == "Entity Resolution":
    con = ingest.connect(True); r = con.execute("select * from resolution order by score").df(); lg_ = con.execute("select * from review_log").df() if "review_log" in [x[0] for x in con.execute("show tables").fetchall()] else pd.DataFrame(); con.close()
    st.write(r.status.value_counts().to_dict()); st.markdown("**Review queue** (score 70–90). Auto ≥90 · Unmatched <70.")
    for x in r[r.status == "review"].itertuples():
        c = st.columns([2, 2, 1, 1, 1, 2, 1]); c[0].write(f"`{x.district_raw}`"); c[1].write(f"→ {x.matched_name}"); c[2].write(f"{x.score:.0f}%")
        if c[3].button("Approve", key="a"+x.district_raw): resolve.decide(x.district_raw, "approve"); st.rerun()
        if c[4].button("Reject", key="r"+x.district_raw): resolve.decide(x.district_raw, "reject"); st.rerun()
        alt = c[5].selectbox("Change to", names, index=names.index(x.matched_name), key="s"+x.district_raw, label_visibility="collapsed")
        if c[6].button("Set", key="c"+x.district_raw): resolve.decide(x.district_raw, "change", m[m.name == alt].id.iloc[0]); st.rerun()
    if st.button("Approve all remaining"): resolve.approve_all_review(); st.rerun()
    st.markdown("**All resolutions** (raw → normalized → canonical, confidence, method, status)"); st.dataframe(r)
    if len(lg_): st.markdown("**Audit trail**"); st.dataframe(lg_)

elif page == "Data Quality":
    con = ingest.connect(True); fa = con.execute("select * from facts").df(); rs = con.execute("select * from resolution").df(); con.close(); rows = []
    for src_, d in fa.groupby("source"):
        rr = rs[rs.district_raw.isin(d.district_raw)]; rows.append({"dataset": src_, "rows": len(d), "missing values": int(d.drop(columns=["district_id"]).isna().sum().sum()), "duplicate (district,year)": int(d.duplicated(["district_raw", "year"]).sum()),
            "entities auto": int((rr.status == "auto").sum()), "needs review": int((rr.status == "review").sum()), "unmatched/rejected": int(rr.status.isin(["unmatched", "rejected"]).sum()), "scheme": d.scheme.iloc[0], "ministry": d.ministry.iloc[0]})
    q = pd.DataFrame(rows); c = st.columns(5); c[0].metric("Datasets", len(q)); c[1].metric("Rows", int(q.rows.sum())); c[2].metric("Districts detected", fa.district_raw.nunique()); c[3].metric("Resolved", int(rs.status.isin(["auto", "approved"]).sum())); c[4].metric("Need review", int((rs.status == "review").sum()))
    st.dataframe(q)
    for x in q.itertuples(): st.write(f"{'✓' if x._6 == 0 else '⚠'} **{x.dataset}** — loaded, schema mapped" + (f", {x._7} entities need review" if x._7 else ", entity resolution complete"))
    st.markdown("**Schema conflicts resolved (raw column → unified)**"); st.dataframe(pd.DataFrame([dict(file=k, scheme=v[0], mapping=", ".join(f"{a}→{b}" for a, b in v[2].items())) for k, v in ingest.MAP.items()]))

else:
    fl = st.selectbox("Source file", sorted(f.source_file.unique())); ok, stored, now = P.verify(fl); (st.success if ok else st.error)("✓ verified" if ok else "✗ TAMPERED"); st.code(f"stored  {stored}\ncurrent {now}")
    c = st.columns(2)
    if c[0].button("Tamper: change one number"): P.tamper(fl); st.rerun()
    if c[1].button("Restore original"): P.restore(fl); st.rerun()
    st.dataframe(f[f.source_file == fl].drop(columns=["district_id", "source"]))
    st.caption("Every insight → source file → row numbers → calculation → Merkle-root integrity check.")
