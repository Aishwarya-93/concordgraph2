import { useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip as LT } from 'react-leaflet'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from 'recharts'
import 'leaflet/dist/leaflet.css'

type Row = Record<string, any>
interface Chart { kind: 'bar' | 'line'; series: string[]; data: Row[] }
const B: string = (import.meta.env.VITE_API_BASE as string) || ''
const api = (u: string) => fetch(B + '/api' + u).then(r => r.json())
const post = (u: string, b?: any) => fetch(B + '/api' + u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b ?? {}) }).then(r => r.json())
const COL = ['#2563eb', '#16a34a', '#dc2626', '#9333ea', '#ea580c']
const PAGES = ['Overview', 'Governance Map', 'Ask ConcordGraph', 'Alerts', 'Convergence', 'Compare', 'Entity Resolution', 'Data Quality', 'Evidence']

function Table({ rows, hide = [], onClick, sel }: { rows: Row[]; hide?: string[]; onClick?: (r: Row, i: number) => void; sel?: number }) {
  if (!rows?.length) return <i>No rows</i>
  const cols = Object.keys(rows[0]).filter(c => !hide.includes(c))
  return <div className="tbl"><table><thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>
    {rows.map((r, i) => <tr key={i} className={(onClick ? 'click ' : '') + (sel === i ? 'sel' : '')} onClick={() => onClick?.(r, i)}>{cols.map(c => <td key={c}>{typeof r[c] === 'number' ? Math.round(r[c] * 1000) / 1000 : String(r[c] ?? '')}</td>)}</tr>)}</tbody></table></div>
}
function Viz({ c }: { c: Chart | null }) {
  if (!c?.data?.length) return null
  const Ch: any = c.kind === 'line' ? LineChart : BarChart
  return <ResponsiveContainer width="100%" height={260}><Ch data={c.data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="x" fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Legend />
    {c.series.map((s, i) => c.kind === 'line' ? <Line key={s} dataKey={s} stroke={COL[i % 5]} /> : <Bar key={s} dataKey={s} fill={COL[i % 5]} />)}</Ch></ResponsiveContainer>
}
function Evidence({ file, rows }: { file: string; rows?: string }) {
  const [e, setE] = useState<any>(null)
  useEffect(() => { if (file && file !== 'facts') api(`/evidence?file=${file}&rows=${rows ?? ''}`).then(setE) }, [file, rows])
  if (!e) return <i>Evidence: derived from facts (see Convergence).</i>
  return <div><div className={e.verified ? 'ok' : 'bad'}>{e.verified ? '✓ Source verified' : '✗ Source changed since snapshot'} — {e.file} <small>{e.current?.slice(0, 12)}…</small></div>
    <details><summary>View source records</summary><Table rows={e.rows} /></details></div>
}

function Graph({ d }: { d: any }) {
  const sc: Row[] = d.schemes, mins = [...new Set(sc.map(s => s.ministry))] as string[], H = Math.max(sc.length, mins.length) * 70 + 40
  const y = (i: number, n: number) => 30 + (i + .5) * ((H - 40) / n), cy = H / 2
  return <svg width="100%" viewBox={`0 0 900 ${H}`} style={{ background: '#fff', borderRadius: 8 }}>
    {sc.map((s, i) => { const mi = mins.indexOf(s.ministry); return <g key={s.scheme}>
      <line x1={190} y1={y(mi, mins.length)} x2={350} y2={y(i, sc.length)} stroke="#94a3b8" /><line x1={470} y1={y(i, sc.length)} x2={600} y2={cy} stroke="#2563eb" strokeWidth={1 + s.spent / 400} />
      <text x={480} y={y(i, sc.length) - 6} fontSize={10}>{s.spent.toFixed(0)} Cr · {(s.utilization * 100).toFixed(0)}%</text>
      <rect x={350} y={y(i, sc.length) - 16} width={120} height={32} rx={8} fill="#dbeafe" /><text x={410} y={y(i, sc.length) + 4} textAnchor="middle" fontSize={12}>{s.scheme}</text></g> })}
    {mins.map((m, i) => <g key={m}><rect x={10} y={y(i, mins.length) - 16} width={180} height={32} rx={8} fill="#e2e8f0" /><text x={100} y={y(i, mins.length) + 4} textAnchor="middle" fontSize={11}>{m}</text></g>)}
    <rect x={600} y={cy - 20} width={120} height={40} rx={8} fill="#fde68a" /><text x={660} y={cy + 5} textAnchor="middle" fontWeight={700}>{d.name}</text>
    <line x1={720} y1={cy} x2={790} y2={cy - 40} stroke="#94a3b8" /><line x1={720} y1={cy} x2={790} y2={cy + 40} stroke="#94a3b8" strokeDasharray="4" />
    <text x={795} y={cy - 36} fontSize={11}>Beneficiaries {Math.round(sc.reduce((a, s) => a + s.beneficiaries, 0)).toLocaleString()}</text><text x={795} y={cy + 44} fontSize={11}>Dev. index {d.development_index}</text></svg>
}

function MapPage({ names }: { names: string[] }) {
  const [metric, setMetric] = useState('spent'), [scheme, setScheme] = useState('All'), [pts, setPts] = useState<Row[]>([]), [sel, setSel] = useState('Nashik'), [d, setD] = useState<any>(null)
  useEffect(() => { api(`/map?scheme=${scheme}&metric=${metric}`).then(setPts) }, [metric, scheme])
  useEffect(() => { api('/district/' + encodeURIComponent(sel)).then(setD) }, [sel])
  const v = pts.map(p => p.value ?? 0), lo = Math.min(...v), hi = Math.max(...v)
  return <>
    <div className="row"><select value={scheme} onChange={e => setScheme(e.target.value)}>{['All', 'MGNREGA', 'PMAY-G', 'JJM'].map(s => <option key={s}>{s}</option>)}</select>
      <select value={metric} onChange={e => setMetric(e.target.value)}>{['spent', 'utilization', 'beneficiaries', 'development_index', 'anomaly_count', 'convergence_schemes'].map(s => <option key={s}>{s}</option>)}</select>
      <select value={sel} onChange={e => setSel(e.target.value)}>{names.map(n => <option key={n}>{n}</option>)}</select><small>Green = higher, red = lower. Click a district.</small></div>
    <MapContainer center={[19, 76.5]} zoom={6} style={{ marginTop: 10 }}><TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="© OpenStreetMap" />
      {pts.map(p => { const t = (hi > lo ? ((p.value ?? 0) - lo) / (hi - lo) : .5); return <CircleMarker key={p.name} center={[p.lat, p.lon]} radius={7 + 14 * t} pathOptions={{ color: p.name === sel ? '#000' : '#fff', weight: p.name === sel ? 3 : 1, fillColor: `rgb(${230 * (1 - t) | 0},${60 + 150 * t | 0},90)`, fillOpacity: .85 }} eventHandlers={{ click: () => setSel(p.name) }}><LT>{p.name}: {p.value}</LT></CircleMarker> })}</MapContainer>
    {d && <div className="card" style={{ marginTop: 14 }}><h3>{d.name} — district intelligence profile</h3>
      <div className="row">{[['Development index (syn.)', d.development_index], ['Population (lakh)', d.population_lakh], ['Allocated Cr', d.schemes.reduce((a: number, s: Row) => a + s.allocated, 0)], ['Spent Cr', d.schemes.reduce((a: number, s: Row) => a + s.spent, 0)], ['Beneficiaries', d.schemes.reduce((a: number, s: Row) => a + s.beneficiaries, 0)]].map(([k, x]) => <div className="kpi card" key={k as string}>{k}<b>{Math.round((x as number) * 10) / 10}</b></div>)}</div>
      {d.convergence && <div className="ans">Potential convergence opportunity: {d.convergence[0].schemes}</div>}
      <h3>Ministry → Scheme → District → Outcome</h3><Graph d={d} /><h3>Scheme breakdown (incl. per-beneficiary metrics)</h3><Table rows={d.schemes} />
      <h3>Utilization trend</h3><Viz c={{ kind: 'line', series: Object.keys(d.trend[0]).filter(k => k !== 'year'), data: d.trend.map((r: Row) => ({ ...r, x: String(r.year) })) }} />
      <h3>Alerts ({d.alerts.length})</h3><Table rows={d.alerts} hide={['why', 'source_file', 'source_rows', 'observed', 'benchmark', 'suggestion']} />
      <details><summary>Peer districts (association only)</summary><Table rows={d.peers} /></details></div>}</>
}

function Ask() {
  const [lang, setLang] = useState('en'), [q, setQ] = useState(''), [ctx, setCtx] = useState<any>(null), [hist, setHist] = useState<{ q: string; r: any }[]>([]), rec = useRef<any>(null)
  const go = async (t = q) => { if (!t.trim()) return; const r = await post('/ask', { q: t, lang, ctx }); if (r.ok) setCtx(r.ctx); setHist([{ q: t, r }, ...hist]); setQ('') }
  const mic = () => { const S = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition; if (!S) return alert('Voice input not supported in this browser (use Chrome/Edge).')
    const r = new S(); r.lang = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' }[lang]; r.onresult = (e: any) => { const t = e.results[0][0].transcript; setQ(t); go(t) }; r.start(); rec.current = r }
  const ex: Record<string, string[]> = { en: ['Which districts have the lowest JJM utilization?', 'Compare Nashik and Pune', 'Which districts have high allocation but low outcomes?'], hi: ['किन जिलों में JJM का उपयोग सबसे कम है?', 'नाशिक जिले में JJM का उपयोग कितना है?'], mr: ['कोणत्या जिल्ह्यांमध्ये JJM चा वापर सर्वात कमी आहे?', 'नाशिक आणि पुणे यांची तुलना करा'] }
  return <>
    <div className="row">{[['en', 'English'], ['hi', 'हिन्दी'], ['mr', 'मराठी']].map(([k, n]) => <button key={k} className={'b ' + (lang === k ? 'pri' : '')} onClick={() => setLang(k)}>{n}</button>)}
      <button className="b" onClick={() => { setHist([]); setCtx(null) }}>Clear conversation</button></div>
    <p><small>Works offline — no API key. Follow-ups ("Compare it with Pune", "What about PMAY-G?") use conversation context.</small></p>
    <div className="row" style={{ marginBottom: 8 }}>{ex[lang].map(e => <button key={e} className="b" onClick={() => go(e)}>{e}</button>)}</div>
    <div className="row"><input style={{ flex: 1 }} value={q} placeholder="Ask a question…" onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && go()} /><button className="b pri" onClick={() => go()}>Ask</button><button className="b" onClick={mic}>🎤</button></div>
    {hist.slice(0, 4).map((h, i) => <div className="card" style={{ marginTop: 12 }} key={i}><b>🧑 {h.q}</b><div className="ans" style={h.r.ok ? {} : { background: '#fff7e0', borderColor: '#f59e0b' }}>{h.r.text}</div>
      {h.r.ok && <><Viz c={h.r.chart} /><Table rows={h.r.rows} /><details><summary>Evidence & SQL</summary><pre>{h.r.sql}</pre><small>language: {h.r.detected} · intent: {h.r.kind}</small><pre>{(h.r.sources || []).join('\n')}</pre></details></>}</div>)}</>
}

function Alerts() {
  const [al, setAl] = useState<Row[]>([]), [t, setT] = useState('All'), [i, setI] = useState(0)
  useEffect(() => { api('/alerts').then(setAl) }, [])
  const types = ['All', ...new Set(al.map(a => a.type))], v = al.filter(a => t === 'All' || a.type === t), a = v[i]
  return <><select value={t} onChange={e => { setT(e.target.value); setI(0) }}>{types.map(x => <option key={x as string}>{x as string}</option>)}</select>
    <div style={{ marginTop: 10 }}><Table rows={v.map(({ district, scheme, type, reason, rupees_cr_at_risk }) => ({ district, scheme, type, reason, rupees_cr_at_risk }))} onClick={(_, k) => setI(k)} sel={i} /></div>
    {a && <div className="card" style={{ marginTop: 12 }}><h3>{a.type}: {a.district}</h3><details open><summary><b>❓ Why am I seeing this?</b></summary><pre>{a.why}</pre></details>
      <p><b>Finding:</b> {a.reason}<br /><b>Recommendation (for investigation):</b> {a.suggestion}<br /><b>Evidence type:</b> rule-based comparison against a peer/state benchmark — an observed pattern; it does not show misuse or cause.</p><Evidence file={a.source_file} rows={a.source_rows} /></div>}</>
}

function Resolution({ names }: { names: string[] }) {
  const [d, setD] = useState<any>(null), [alt, setAlt] = useState<Record<string, string>>({}), load = () => api('/resolution').then(setD); useEffect(() => { load() }, [])
  const act = async (raw: string, action: string) => { await post('/resolution/decide', { raw, action, new_name: alt[raw] }); load() }
  if (!d) return null; const rv = d.rows.filter((r: Row) => r.status === 'review')
  return <><div className="card"><h3>Review queue (score 70–90) — {rv.length} pending</h3><table><thead><tr><th>Raw</th><th>Suggested</th><th>Confidence</th><th>Action</th></tr></thead><tbody>{rv.map((r: Row) => <tr key={r.district_raw}><td>{r.district_raw}</td><td>{r.matched_name}</td><td>{r.score}%</td>
    <td><button className="b" onClick={() => act(r.district_raw, 'approve')}>Approve</button> <button className="b" onClick={() => act(r.district_raw, 'reject')}>Reject</button> <select value={alt[r.district_raw] ?? r.matched_name} onChange={e => setAlt({ ...alt, [r.district_raw]: e.target.value })}>{names.map(n => <option key={n}>{n}</option>)}</select> <button className="b" onClick={() => act(r.district_raw, 'change')}>Set</button></td></tr>)}</tbody></table></div>
    <div className="card"><h3>All resolutions</h3><Table rows={d.rows} /></div>{d.log.length > 0 && <div className="card"><h3>Audit trail</h3><Table rows={d.log} /></div>}</>
}

function EvidencePage({ files }: { files: string[] }) {
  const [f, setF] = useState(files[0]), [n, setN] = useState(0), [e, setE] = useState<any>(null)
  useEffect(() => { if (f) api(`/evidence?file=${f}`).then(setE) }, [f, n])
  const act = async (a: string) => { await post(`/provenance/${a}?file=${f}`); setN(n + 1) }
  return <><select value={f} onChange={x => setF(x.target.value)}>{files.map(x => <option key={x}>{x}</option>)}</select>
    {e && <div className="card" style={{ marginTop: 10 }}><div className={e.verified ? 'ok' : 'bad'}>{e.verified ? '✓ Verified' : '✗ TAMPERED'}</div><pre>stored  {e.stored}{'\n'}current {e.current}</pre>
      <button className="b" onClick={() => act('tamper')}>Tamper: change one number</button> <button className="b" onClick={() => act('restore')}>Restore original</button>
      <p><small>Insight → source file → row numbers → calculation → Merkle-root integrity check.</small></p><Table rows={e.rows} /></div>}</>
}

export default function App() {
  const [p, setP] = useState('Overview'), [o, setO] = useState<any>(null), [cv, setCv] = useState<Row[]>([]), [q, setQ] = useState<Row[]>([]), [cmp, setCmp] = useState<Row[]>([]), [pick, setPick] = useState(['Nashik', 'Pune'])
  useEffect(() => { api('/overview').then(setO) }, [])
  useEffect(() => { if (p === 'Convergence') api('/convergence').then(setCv); if (p === 'Data Quality') api('/quality').then(setQ); if (p === 'Compare') api('/compare?names=' + pick.join(',')).then(setCmp) }, [p, pick])
  return <><div className="side"><h2>ConcordGraph</h2>{PAGES.map(x => <button key={x} className={p === x ? 'on' : ''} onClick={() => setP(x)}>{x}</button>)}</div>
    <div className="main"><div className="warn">Demo data is <b>synthetic</b>. Findings are associations / patterns to investigate, not causal claims.</div>
      {!o ? 'Loading…' : <>
        {p === 'Overview' && <><h2>ConcordGraph</h2><p>A unified, explainable and traceable relationship layer across fragmented government programmes — finds cross-scheme gaps, anomalies and convergence opportunities, searchable in English, हिन्दी and मराठी.</p>
          <div className="row">{[['Districts', o.districts], ['Schemes', o.schemes], ['Ministries', o.ministries], ['Alerts', o.alerts], ['Convergence districts', o.convergence]].map(([k, v]) => <div key={k as string} className="card kpi">{k}<b>{v}</b></div>)}</div>
          <div className="card">Pipeline: heterogeneous CSVs → entity resolution (human review) → DuckDB → analytics → recommendations → multilingual NLQ → evidence &amp; integrity verification.</div></>}
        {p === 'Governance Map' && <MapPage names={o.districts_list} />}{p === 'Ask ConcordGraph' && <Ask />}{p === 'Alerts' && <Alerts />}
        {p === 'Convergence' && <><p>Districts where 2+ schemes (across ministries) are in the top quartile of allocation per lakh people — a <b>potential convergence opportunity</b>, not proof of (un)coordination. No beneficiary IDs exist, so beneficiary-level overlap is not measured.</p><Table rows={cv} hide={['status']} /></>}
        {p === 'Compare' && <><div className="row">{[0, 1, 2].map(i => <select key={i} value={pick[i] ?? ''} onChange={e => setPick(pick.map((x, j) => j === i ? e.target.value : x).concat(pick.length <= i ? [e.target.value] : []).filter(Boolean))}><option value="">—</option>{o.districts_list.map((n: string) => <option key={n}>{n}</option>)}</select>)}</div><div style={{ marginTop: 10 }}><Table rows={cmp} /></div><small>Side-by-side facts only — no best/worst ranking implied.</small></>}
        {p === 'Entity Resolution' && <Resolution names={o.districts_list} />}
        {p === 'Data Quality' && <Table rows={q} />}{p === 'Evidence' && <EvidencePage files={o.files} />}</>}</div></>
}
