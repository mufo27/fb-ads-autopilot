"use client";
import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type AdSet = { id: number; name: string; product: string | null; daily_budget: number;
  spend: number; conversions: number; revenue: number; in_learning: boolean; status: string; roas: number };
type Decision = { id: number; ts: string; action: string; verdict: string; reason: string; guardrail_rule: string; applied: boolean };
type Guard = { daily_hard_cap: number; per_campaign_cap: number; velocity_window_min: number;
  velocity_max_pct: number; min_roas: number; learning_min_conv: number; dry_run: boolean;
  spend_today: number; remaining_today: number };

const NAV = [
  { group: "ภาพรวม", items: [ { id: "overview", ico: "📊", label: "แดชบอร์ด" }, { id: "adsets", ico: "🎯", label: "Ad Sets" } ] },
  { group: "ควบคุม", items: [ { id: "guardrails", ico: "🛡️", label: "กรอบเหล็ก" }, { id: "log", ico: "🧾", label: "บันทึก AI" } ] },
  { group: "ตั้งค่า", items: [ { id: "keys", ico: "🔑", label: "Connect Keys" } ] },
];

export default function Dashboard() {
  const [guard, setGuard] = useState<Guard | null>(null);
  const [adsets, setAdsets] = useState<AdSet[]>([]);
  const [active, setActive] = useState(0);
  const [killed, setKilled] = useState(false);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [msg, setMsg] = useState("");
  const [msgKind, setMsgKind] = useState("info");
  const [busy, setBusy] = useState(false);
  const [cred, setCred] = useState<Record<string, string>>({});
  const [cstatus, setCstatus] = useState<Record<string, any>>({});
  const [authed, setAuthed] = useState(false);
  const [view, setView] = useState("overview");
  const [showBanner, setShowBanner] = useState(true);
  const tokenRef = useRef("");

  async function api(path: string, opts: RequestInit = {}) {
    const r = await fetch(API + path, { ...opts, headers: { ...(opts.headers || {}), "X-Admin-Token": tokenRef.current } });
    if (r.status === 403) { setAuthed(false); throw new Error("access token ไม่ถูกต้อง (403)"); }
    if (r.status === 429) { throw new Error("เรียกถี่เกินไป รอสักครู่แล้วลองใหม่ (429)"); }
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  }

  const load = useCallback(async () => {
    try {
      const [g, o, d, st] = await Promise.all([
        api("/api/guardrails"), api("/api/overview"), api("/api/decisions?limit=30"), api("/api/settings"),
      ]);
      setGuard(g); setAdsets(o.ad_sets || []); setActive(o.active_campaigns || 0);
      setKilled(!!o.killed); setDecisions(d); setCstatus(st.fields || {});
    } catch (e: any) { toast(e.message, "err"); }
  }, []);

  useEffect(() => { const saved = typeof window !== "undefined" ? localStorage.getItem("adsAdminToken") || "" : ""; if (saved) { tokenRef.current = saved; setAuthed(true); } }, []);
  useEffect(() => { if (authed) { load(); const t = setInterval(load, 15000); return () => clearInterval(t); } }, [authed, load]);

  function toast(m: string, kind = "info") { setMsg(m); setMsgKind(kind); }
  async function act(fn: () => Promise<void>) { setBusy(true); try { await fn(); } catch (e: any) { toast("ผิดพลาด: " + e.message, "err"); } finally { setBusy(false); } }

  const doSync = () => act(async () => { const r = await api("/api/sync", { method: "POST" }); toast(r.ok ? `🔄 sync Meta แล้ว ${r.synced} ad sets` : "sync: " + (r.skipped || r.error), r.ok ? "info" : "warn"); await load(); });
  const seed = () => act(async () => { await api("/api/demo/seed", { method: "POST" }); await load(); toast("seed ข้อมูลตัวอย่างแล้ว"); });
  const run = () => act(async () => { const r = await api("/api/autopilot/run", { method: "POST" }); toast(r.killed ? "หยุดอยู่ (kill switch ON)" : `AI ตัดสินใจ ${r.cycle.length} รายการ`); await load(); });
  const toggleKill = () => act(async () => { const r = await api(`/api/kill?on=${!killed}`, { method: "POST" }); setKilled(r.killed); toast(r.killed ? "🛑 KILL SWITCH ON — AI ถูกสั่งหยุด + pause บน Meta" : "✅ กลับมาทำงานปกติ", r.killed ? "warn" : "info"); await load(); });
  const saveGuard = () => act(async () => { if (!guard) return; const body = { daily_hard_cap: guard.daily_hard_cap, per_campaign_cap: guard.per_campaign_cap, min_roas: guard.min_roas, velocity_max_pct: guard.velocity_max_pct, dry_run: guard.dry_run }; const r = await api("/api/guardrails", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); setGuard(r.config); toast("บันทึกกรอบเหล็กแล้ว"); });
  const saveCreds = () => act(async () => { const payload = Object.fromEntries(Object.entries(cred).filter(([, v]) => v && v.trim() !== "")); if (!payload.length) { toast("ยังไม่ได้พิมพ์ค่าใหม่"); return; } const r = await api("/api/settings", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }); setCstatus(r.fields); setCred({}); toast("✅ บันทึกลง DB (เข้ารหัส) เรียบร้อย"); });

  const login = () => { if (!tokenRef.current) { toast("กรุณาใส่ access token", "warn"); return; } localStorage.setItem("adsAdminToken", tokenRef.current); setMsg(""); setAuthed(true); };
  const logout = () => { localStorage.removeItem("adsAdminToken"); tokenRef.current = ""; setAuthed(false); };
  const set = (k: keyof Guard, v: any) => setGuard((g) => (g ? { ...g, [k]: v } : g));
  const pct = guard ? Math.min(100, (guard.spend_today / (guard.daily_hard_cap || 1)) * 100) : 0;
  const credField = (name: string) => {
    const st = cstatus[name] || {}; const isSecret = !!st.secret;
    const ph = st.is_set ? (isSecret ? `••••${(st.preview || "").slice(-4)} · พิมพ์ทับถ้าจะเปลี่ยน` : st.preview) : "ยังไม่ได้ใส่";
    return (<div className="field" key={name}><label>{st.label || name}</label>
      <input type={isSecret ? "password" : "text"} autoComplete="off" placeholder={ph} value={cred[name] || ""}
        onChange={(e) => setCred((c) => ({ ...c, [name]: e.target.value }))} /></div>);
  };

  if (!authed) {
    return (
      <div className="login-wrap">
        <div className="login-card">
          <div className="brand" style={{ padding: 0, marginBottom: 18 }}><div className="logo" /><div><b>FB Ads Autopilot</b><div className="sub">เข้าสู่ระบบเพื่อจัดการแอด</div></div></div>
          <label>Access Token</label>
          <input type="password" autoComplete="off" placeholder="วาง access token ของคุณ" onChange={(e) => (tokenRef.current = e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") login(); }} />
          {msg && <div className={`toast ${msgKind === "err" ? "err" : "warn"}`} style={{ marginTop: 12 }}>{msg}</div>}
          <button className="btn-green" style={{ width: "100%", marginTop: 16 }} onClick={login}>เข้าระบบ</button>
          <div className="muted" style={{ marginTop: 12, fontSize: 12 }}>ระบบล็อกไว้ทั้งหมดถ้ายังไม่ได้ตั้ง ADMIN_TOKEN (fail-closed)</div>
        </div>
      </div>
    );
  }

  const titles: Record<string, [string, string]> = {
    overview: ["แดชบอร์ด", "ภาพรวมการใช้เงินและสถานะระบบ AI"],
    adsets: ["Ad Sets", "ผลงานราย ad set และ ROAS"],
    guardrails: ["กรอบเหล็ก (Guardrails)", "เพดานเงินและกฎที่ AI ข้ามไม่ได้"],
    log: ["บันทึก AI", "Audit log ทุกการตัดสินใจ"],
    keys: ["Connect Keys", "กรอก Meta / AI token ของคุณ (เข้ารหัสเก็บในฐานข้อมูล)"],
  };
  const [title, desc] = titles[view];

  return (
    <div>
      {showBanner && (
        <div className="banner">
          <span>👋 ยินดีต้อนรับ — ระบบ AI ยิงแอดอัตโนมัติ ทำงานภายใต้กรอบเหล็กที่คุณตั้งไว้เสมอ</span>
          <button className="x" onClick={() => setShowBanner(false)}>×</button>
        </div>
      )}
      <div className="app">
        <aside className="sidebar">
          <div className="brand"><div className="logo" /><div><b>Autopilot</b><div className="sub">FB Ads · AI</div></div></div>
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="nav-group">{g.group}</div>
              {g.items.map((it) => (
                <button key={it.id} className={`nav-item ${view === it.id ? "active" : ""}`} onClick={() => setView(it.id)}>
                  <span className="ico">{it.ico}</span>{it.label}
                  {it.id === "adsets" && <span className="nav-badge">{adsets.length}</span>}
                  {it.id === "log" && <span className="nav-badge">{decisions.length}</span>}
                </button>
              ))}
            </div>
          ))}
          <div style={{ marginTop: "auto", padding: "10px 8px" }}>
            <span className={`chip ${guard?.dry_run ? "yellow" : "red"}`}>{guard?.dry_run ? "DRY-RUN" : "LIVE"}</span>{" "}
            {killed && <span className="chip red">KILLED</span>}
          </div>
        </aside>

        <main className="main">
          <div className="pagehead">
            <div><h1>{title}</h1><div className="desc">{desc}</div></div>
            <div className="actions">
              <button className="btn-outline" onClick={doSync} disabled={busy}>🔄 Sync Meta</button>
              <button className="btn-outline" onClick={seed} disabled={busy}>Seed ตัวอย่าง</button>
              <button className="btn-green" onClick={run} disabled={busy}>▶ รัน AI</button>
              <button className={killed ? "btn-green" : "btn-red"} onClick={toggleKill} disabled={busy}>{killed ? "▶ ทำงานต่อ" : "🛑 Kill"}</button>
              <button className="btn-outline" onClick={logout}>ออกจากระบบ</button>
            </div>
          </div>

          {msg && <div className={`toast ${msgKind === "err" ? "err" : msgKind === "warn" ? "warn" : ""}`}>{msg}</div>}
          {killed && <div className="toast err">🛑 KILL SWITCH ON — AI ห้ามใช้เงินทุกกรณี (กด “ทำงานต่อ” เพื่อปลดล็อก)</div>}
          {!killed && guard && <div className={`toast ${guard.dry_run ? "warn" : "err"}`}>{guard.dry_run ? "🟡 DRY-RUN: AI วิเคราะห์+log อย่างเดียว ยังไม่ยิงเงินจริง" : "🔴 LIVE MODE: AI กำลังยิงแอดจริงตามงบที่กำหนด"}</div>}

          {view === "overview" && (
            <>
              <div className="grid g4">
                <div className="card kpi"><div className="top"><span className="l">ใช้เงินวันนี้</span><span className="chip">THB</span></div>
                  <div className="v green">{guard?.spend_today?.toLocaleString?.() ?? "-"}</div>
                  <div className="bar"><span style={{ width: pct + "%" }} /></div>
                  <div className="foot">เพดาน {guard?.daily_hard_cap?.toLocaleString?.()} · เหลือ {guard?.remaining_today?.toLocaleString?.()}</div></div>
                <div className="card kpi"><div className="top"><span className="l">Campaign Active</span></div><div className="v">{active}</div><div className="foot">กามเปญที่เปิดอยู่</div></div>
                <div className="card kpi"><div className="top"><span className="l">Ad Sets</span></div><div className="v">{adsets.length}</div><div className="foot">กำลังติดตามโดย AI</div></div>
                <div className="card kpi"><div className="top"><span className="l">โหมด</span></div><div className={`v ${guard?.dry_run ? "muted" : "red"}`}>{guard?.dry_run ? "DRY-RUN" : "LIVE"}</div><div className="foot">{guard?.dry_run ? "ปลอดภัย ยังไม่ยิงจริง" : "ยิงเงินจริง"}</div></div>
              </div>
              <div className="card section-gap">
                <h3>Ad Sets ล่าสุด</h3>
                <AdSetTable adsets={adsets} minRoas={guard?.min_roas || 0} />
              </div>
            </>
          )}

          {view === "adsets" && <div className="card"><h3>Ad Sets · ROAS</h3><AdSetTable adsets={adsets} minRoas={guard?.min_roas || 0} /></div>}

          {view === "guardrails" && (
            <div className="card" style={{ maxWidth: 720 }}>
              <h3>ปรับกรอบเหล็ก</h3>
              <div className="row">
                <div className="field"><label>งบรายวัน hard cap (THB)</label><input type="number" value={guard?.daily_hard_cap ?? ""} onChange={(e) => set("daily_hard_cap", +e.target.value)} /></div>
                <div className="field"><label>เพดานต่อกามเปญ</label><input type="number" value={guard?.per_campaign_cap ?? ""} onChange={(e) => set("per_campaign_cap", +e.target.value)} /></div>
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                <div className="field"><label>ROAS ขั้นต่ำ (auto-pause)</label><input type="number" step="0.1" value={guard?.min_roas ?? ""} onChange={(e) => set("min_roas", +e.target.value)} /></div>
                <div className="field"><label>Velocity max %</label><input type="number" value={guard?.velocity_max_pct ?? ""} onChange={(e) => set("velocity_max_pct", +e.target.value)} /></div>
              </div>
              <div className="row" style={{ marginTop: 16, justifyContent: "space-between" }}>
                <label className="switch"><input type="checkbox" checked={guard?.dry_run ?? true} onChange={(e) => set("dry_run", e.target.checked)} /> DRY-RUN mode (ยังไม่ยิงจริง)</label>
                <button className="btn-green" onClick={saveGuard} disabled={busy}>บันทึกกรอบ</button>
              </div>
              <div className="hint" style={{ marginTop: 10 }}>hard cap ถูกจำกัดเพดานบนด้วย SYSTEM_MAX_DAILY_CAP — AI และหน้าจอขยายเกินไม่ได้</div>
            </div>
          )}

          {view === "log" && (
            <div className="card"><h3>AI Decision Log</h3>
              <table><thead><tr><th>เวลา</th><th>Action</th><th>คำวินิจฉัย</th><th>กฎ</th><th>เหตุผล</th></tr></thead>
                <tbody>{decisions.map((d) => (
                  <tr key={d.id}><td className="muted">{new Date(d.ts).toLocaleTimeString("th-TH")}</td><td>{d.action}</td>
                    <td><span className={`pill ${d.verdict === "ALLOW" ? "allow" : d.verdict === "PAUSE" ? "pause" : "block"}`}>{d.verdict}</span></td>
                    <td className="muted">{d.guardrail_rule}</td><td>{d.reason}</td></tr>))}
                  {decisions.length === 0 && <tr><td colSpan={5} className="muted">ยังไม่มีบันทึก — กด “รัน AI”</td></tr>}
                </tbody></table>
            </div>
          )}

          {view === "keys" && (
            <div className="card" style={{ maxWidth: 820 }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
                <h3 style={{ margin: 0 }}>กรอก key / token ของคุณ</h3>
                <button className="btn-green" onClick={saveCreds} disabled={busy}>บันทึก &amp; เข้ารหัสลง DB</button>
              </div>
              <div className="hint" style={{ marginBottom: 14 }}>เว้นว่างช่องที่เป็น •••• = ใช้ค่าเดิม · ค่าลับถูก AES-encrypt ก่อนเขียนลงฐานข้อมูล</div>
              <div className="row">{credField("META_APP_ID")}{credField("META_AD_ACCOUNT_ID")}{credField("META_PAGE_ID")}</div>
              <div className="row" style={{ marginTop: 12 }}>{credField("META_APP_SECRET")}{credField("META_PAGE_ACCESS_TOKEN")}{credField("META_MARKETING_TOKEN")}</div>
              <div className="row" style={{ marginTop: 12 }}>{credField("AI_PROVIDER")}{credField("AI_MODEL")}{credField("AI_API_KEY")}</div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function AdSetTable({ adsets, minRoas }: { adsets: AdSet[]; minRoas: number }) {
  return (
    <table>
      <thead><tr><th>ชื่อ</th><th>สินค้า</th><th>งบ/วัน</th><th>จ่ายแล้ว</th><th>ROAS</th><th>สถานะ</th></tr></thead>
      <tbody>
        {adsets.map((a) => (
          <tr key={a.id}><td>{a.name}</td><td>{a.product || "-"}</td>
            <td>{Number(a.daily_budget).toLocaleString()}</td><td>{Number(a.spend).toLocaleString()}</td>
            <td><span className={`pill ${a.in_learning ? "learn" : a.roas >= minRoas ? "good" : "bad"}`}>{a.in_learning ? "Learning" : a.roas.toFixed(2)}</span></td>
            <td><span className={`pill ${a.status === "ACTIVE" ? "good" : "pause"}`}>{a.status}</span></td></tr>))}
        {adsets.length === 0 && <tr><td colSpan={6} className="muted">ยังไม่มีข้อมูล — กด “Seed ตัวอย่าง” หรือ “Sync Meta”</td></tr>}
      </tbody>
    </table>
  );
}
