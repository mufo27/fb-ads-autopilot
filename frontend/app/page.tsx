"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "./icons";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type AdSet = { id: number; name: string; product: string | null; daily_budget: number;
  spend: number; conversions: number; revenue: number; in_learning: boolean; status: string; roas: number };
type Decision = { id: number; ts: string; action: string; verdict: string; reason: string; guardrail_rule: string; applied: boolean };
type Guard = { daily_hard_cap: number; per_campaign_cap: number; velocity_window_min: number;
  velocity_max_pct: number; min_roas: number; learning_min_conv: number; dry_run: boolean;
  spend_today: number; remaining_today: number };
type User = { id: number; email: string; name: string; role: string; provider?: string };

const NAV = [
  { group: "ภาพรวม", items: [ { id: "overview", ico: "dashboard", label: "แดชบอร์ด" }, { id: "adsets", ico: "target", label: "Ad Sets" } ] },
  { group: "ควบคุม", items: [ { id: "guardrails", ico: "shield", label: "กรอบเหล็ก" }, { id: "log", ico: "list", label: "บันทึก AI" } ] },
  { group: "ตั้งค่า", items: [ { id: "profile", ico: "user", label: "โปรไฟล์" }, { id: "keys", ico: "key", label: "Connect Keys" } ] },
];

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
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
  const [view, setView] = useState("overview");
  const [showBanner, setShowBanner] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [pname, setPname] = useState("");
  const [pwOld, setPwOld] = useState(""); const [pwNew, setPwNew] = useState(""); const [pwConfirm, setPwConfirm] = useState("");

  async function api(path: string, opts: RequestInit = {}) {
    const r = await fetch(API + path, { credentials: "include", ...opts, headers: { ...(opts.headers || {}) } });
    if (r.status === 401) { router.replace("/login"); throw new Error("ต้องเข้าสู่ระบบ"); }
    if (r.status === 429) { throw new Error("เรียกถี่เกินไป รอสักครู่แล้วลองใหม่ (429)"); }
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  }

  // verify session on mount
  useEffect(() => {
    fetch(`${API}/api/auth/me`, { credentials: "include" })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(d => { setUser(d.user); setPname(d.user.name || ""); setChecking(false); })
      .catch(() => router.replace("/login"));
  }, [router]);

  const load = useCallback(async () => {
    try {
      const [g, o, d, st] = await Promise.all([
        api("/api/guardrails"), api("/api/overview"), api("/api/decisions?limit=30"), api("/api/settings"),
      ]);
      setGuard(g); setAdsets(o.ad_sets || []); setActive(o.active_campaigns || 0);
      setKilled(!!o.killed); setDecisions(d); setCstatus(st.fields || {});
    } catch (e: any) { toast(e.message, "err"); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { if (user) { load(); const t = setInterval(load, 15000); return () => clearInterval(t); } }, [user, load]);

  // sidebar: จำสถานะพับใน localStorage + พับอัตโนมัติเมื่อจอแคบ (ถ้ายังไม่เคยตั้ง)
  const GROUPS = NAV.map((g) => g.group);
  useEffect(() => {
    let saved: Record<string, boolean> | null = null;
    try { saved = JSON.parse(localStorage.getItem("sidebarCollapsed") || "null"); } catch {}
    if (saved) { setCollapsed(saved); }
    else if (typeof window !== "undefined" && window.innerWidth < 1024) {
      setCollapsed(Object.fromEntries(GROUPS.map((g) => [g, true])));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const toggleGroup = (grp: string) => setCollapsed((c) => {
    const n = { ...c, [grp]: !c[grp] };
    try { localStorage.setItem("sidebarCollapsed", JSON.stringify(n)); } catch {}
    return n;
  });

  function toast(m: string, kind = "info") { setMsg(m); setMsgKind(kind); }
  async function act(fn: () => Promise<void>) { setBusy(true); try { await fn(); } catch (e: any) { toast("ผิดพลาด: " + e.message, "err"); } finally { setBusy(false); } }

  const doSync = () => act(async () => { const r = await api("/api/sync", { method: "POST" }); toast(r.ok ? `Sync Meta แล้ว ${r.synced} ad sets` : "sync: " + (r.skipped || r.error), r.ok ? "info" : "warn"); await load(); });
  const seed = () => act(async () => { await api("/api/demo/seed", { method: "POST" }); await load(); toast("เพิ่มข้อมูลตัวอย่างแล้ว"); });
  const run = () => act(async () => { const r = await api("/api/autopilot/run", { method: "POST" }); toast(r.killed ? "หยุดอยู่ (kill switch ON)" : `AI ตัดสินใจ ${r.cycle.length} รายการ`); await load(); });
  const toggleKill = () => act(async () => { const r = await api(`/api/kill?on=${!killed}`, { method: "POST" }); setKilled(r.killed); toast(r.killed ? "KILL SWITCH ON — AI ถูกสั่งหยุด + pause บน Meta" : "กลับมาทำงานปกติแล้ว", r.killed ? "warn" : "info"); await load(); });
  const saveGuard = () => act(async () => { if (!guard) return; const body = { daily_hard_cap: guard.daily_hard_cap, per_campaign_cap: guard.per_campaign_cap, min_roas: guard.min_roas, velocity_max_pct: guard.velocity_max_pct, dry_run: guard.dry_run }; const r = await api("/api/guardrails", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); setGuard(r.config); toast("บันทึกกรอบเหล็กแล้ว"); });
  const saveCreds = () => act(async () => { const payload = Object.fromEntries(Object.entries(cred).filter(([, v]) => v && v.trim() !== "")); if (!payload.length) { toast("ยังไม่ได้พิมพ์ค่าใหม่"); return; } const r = await api("/api/settings", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }); setCstatus(r.fields); setCred({}); toast("บันทึก & เข้ารหัสลง DB เรียบร้อย"); });

  const logout = async () => { try { await fetch(`${API}/api/auth/logout`, { method: "POST", credentials: "include" }); } catch {} router.replace("/login"); };
  const saveProfile = () => act(async () => { const r = await api("/api/auth/profile", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: pname }) }); setUser(r.user); toast("บันทึกโปรไฟล์แล้ว"); });
  const savePw = () => act(async () => { if (pwNew !== pwConfirm) { toast("รหัสผ่านใหม่และการยืนยันไม่ตรงกัน", "warn"); return; } await api("/api/auth/change-password", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ old_password: pwOld, new_password: pwNew }) }); setPwOld(""); setPwNew(""); setPwConfirm(""); toast("เปลี่ยนรหัสผ่านเรียบร้อย"); });
  const set = (k: keyof Guard, v: any) => setGuard((g) => (g ? { ...g, [k]: v } : g));
  const pct = guard ? Math.min(100, (guard.spend_today / (guard.daily_hard_cap || 1)) * 100) : 0;
  const credField = (name: string) => {
    const st = cstatus[name] || {}; const isSecret = !!st.secret;
    const ph = st.is_set ? (isSecret ? `••••${(st.preview || "").slice(-4)} · พิมพ์ทับถ้าจะเปลี่ยน` : st.preview) : "ยังไม่ได้ใส่";
    return (<div className="field" key={name}><label>{st.label || name}</label>
      <input type={isSecret ? "password" : "text"} autoComplete="off" placeholder={ph} value={cred[name] || ""}
        onChange={(e) => setCred((c) => ({ ...c, [name]: e.target.value }))} /></div>);
  };

  if (checking) return <div className="flex items-center justify-center min-h-screen text-muted">กำลังตรวจสอบสถานะ…</div>;

  const titles: Record<string, [string, string]> = {
    overview: ["แดชบอร์ด", "ภาพรวมการใช้เงินและสถานะระบบ AI"],
    adsets: ["Ad Sets", "ผลงานราย ad set และ ROAS"],
    guardrails: ["กรอบเหล็ก (Guardrails)", "เพดานเงินและกฎที่ AI ข้ามไม่ได้"],
    log: ["บันทึก AI", "Audit log ทุกการตัดสินใจ"],
    profile: ["โปรไฟล์", "ข้อมูลบัญชีและการเปลี่ยนรหัสผ่าน"],
    keys: ["Connect Keys", "กรอก Meta / AI token ของคุณ (เข้ารหัสเก็บในฐานข้อมูล)"],
  };
  const [title, desc] = titles[view];
  const initial = (user?.name || user?.email || "?").trim().charAt(0).toUpperCase();

  return (
    <div>
      {showBanner && (
        <div className="banner">
          <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}><Icon name="sparkles" size={16} /> ยินดีต้อนรับ{user?.name ? ` คุณ${user.name}` : ""} — ระบบ AI ยิงแอดอัตโนมัติ ทำงานภายใต้กรอบเหล็กที่คุณตั้งไว้เสมอ</span>
          <button className="x" onClick={() => setShowBanner(false)}>×</button>
        </div>
      )}
      <div className="app">
        <aside className="sidebar">
          <div className="brand"><div className="logo" /><div><b>Autopilot</b><div className="sub">FB Ads · AI</div></div></div>
          {NAV.map((g) => {
            const closed = !!collapsed[g.group];
            return (
            <div key={g.group}>
              <button className={`nav-group ${closed ? "closed" : ""}`} onClick={() => toggleGroup(g.group)}>
                {g.group}<span className="chev"><Icon name="chevron" size={15} /></span>
              </button>
              {!closed && g.items.map((it) => (
                <button key={it.id} className={`nav-item ${view === it.id ? "active" : ""}`} onClick={() => setView(it.id)}>
                  <span className="ico"><Icon name={it.ico} size={17} /></span>{it.label}
                  {it.id === "adsets" && <span className="nav-badge">{adsets.length}</span>}
                  {it.id === "log" && <span className="nav-badge">{decisions.length}</span>}
                </button>
              ))}
            </div>
            );
          })}
          <div style={{ marginTop: "auto", padding: "10px 12px 4px" }}>
            <span className={`chip ${guard?.dry_run ? "yellow" : "red"}`}>{guard?.dry_run ? "DRY-RUN" : "LIVE"}</span>{" "}
            {killed && <span className="chip red">KILLED</span>}
          </div>
          <div className="profile">
            {menuOpen && (
              <div className="menu">
                <button className="menu-i" onClick={() => { setView("profile"); setMenuOpen(false); }}><Icon name="user" size={16} /> โปรไฟล์</button>
                <button className="menu-i" onClick={() => { setView("keys"); setMenuOpen(false); }}><Icon name="key" size={16} /> การเชื่อมต่อ</button>
                <button className="menu-i" onClick={() => { setView("guardrails"); setMenuOpen(false); }}><Icon name="shield" size={16} /> ตั้งค่ากรอบเหล็ก</button>
                <div className="sep" />
                <button className="menu-i" onClick={logout}><Icon name="logout" size={16} /> ออกจากระบบ</button>
              </div>
            )}
            <button className="profile-btn" onClick={() => setMenuOpen((v) => !v)}>
              <div className="avatar">{initial}</div>
              <div style={{ minWidth: 0 }}><div className="pname">{user?.name || "ผู้ใช้"}</div><div className="pmail">{user?.email}</div></div>
            </button>
          </div>
        </aside>

        <main className="main">
          <div className="pagehead">
            <div><h1>{title}</h1><div className="desc">{desc}</div></div>
            <div className="actions">
              <button className="btn-outline" onClick={doSync} disabled={busy}><Icon name="refresh" size={16} /> Sync Meta</button>
              <button className="btn-outline" onClick={seed} disabled={busy}><Icon name="box" size={16} /> Seed ตัวอย่าง</button>
              <button className="btn-green" onClick={run} disabled={busy}><Icon name="play" size={16} /> รัน AI</button>
              <button className={killed ? "btn-green" : "btn-red"} onClick={toggleKill} disabled={busy}><Icon name="power" size={16} /> {killed ? "ทำงานต่อ" : "Kill"}</button>
            </div>
          </div>

          {msg && <div className={`toast ${msgKind === "err" ? "err" : msgKind === "warn" ? "warn" : ""}`}><Icon name={msgKind === "info" ? "check" : "alert"} size={16} /> {msg}</div>}
          {killed && <div className="toast err"><Icon name="power" size={16} /> KILL SWITCH ON — AI ห้ามใช้เงินทุกกรณี (กด “ทำงานต่อ” เพื่อปลดล็อก)</div>}
          {!killed && guard && <div className={`toast ${guard.dry_run ? "warn" : "err"}`}><Icon name={guard.dry_run ? "shield" : "alert"} size={16} /> {guard.dry_run ? "DRY-RUN: AI วิเคราะห์+log อย่างเดียว ยังไม่ยิงเงินจริง" : "LIVE MODE: AI กำลังยิงแอดจริงตามงบที่กำหนด"}</div>}

          {view === "overview" && (
            <>
              <div className="grid g4">
                <div className="card kpi"><div className="top"><span className="l"><Icon name="coins" size={15} /> ใช้เงินวันนี้</span><span className="chip">THB</span></div>
                  <div className="v green">{guard?.spend_today?.toLocaleString?.() ?? "-"}</div>
                  <div className="bar"><span style={{ width: pct + "%" }} /></div>
                  <div className="foot">เพดาน {guard?.daily_hard_cap?.toLocaleString?.()} · เหลือ {guard?.remaining_today?.toLocaleString?.()}</div></div>
                <div className="card kpi"><div className="top"><span className="l"><Icon name="box" size={15} /> Campaign Active</span></div><div className="v">{active}</div><div className="foot">กามเปญที่เปิดอยู่</div></div>
                <div className="card kpi"><div className="top"><span className="l"><Icon name="target" size={15} /> Ad Sets</span></div><div className="v">{adsets.length}</div><div className="foot">กำลังติดตามโดย AI</div></div>
                <div className="card kpi"><div className="top"><span className="l"><Icon name="shield" size={15} /> โหมด</span></div><div className={`v ${guard?.dry_run ? "muted" : "red"}`}>{guard?.dry_run ? "DRY-RUN" : "LIVE"}</div><div className="foot">{guard?.dry_run ? "ปลอดภัย ยังไม่ยิงจริง" : "ยิงเงินจริง"}</div></div>
              </div>
              <div className="card section-gap">
                <h3>Ad Sets ล่าสุด</h3>
                <AdSetTable adsets={adsets} minRoas={guard?.min_roas || 0} onSeed={seed} />
              </div>
            </>
          )}

          {view === "adsets" && <div className="card"><h3>Ad Sets · ROAS</h3><AdSetTable adsets={adsets} minRoas={guard?.min_roas || 0} onSeed={seed} /></div>}

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

          {view === "profile" && (
            <div className="grid g2" style={{ alignItems: "start" }}>
              <div className="card">
                <h3>บัญชีของฉัน</h3>
                <div className="row" style={{ gap: 14, marginBottom: 18 }}>
                  <div className="avatar" style={{ width: 56, height: 56, fontSize: 22 }}>{initial}</div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 16 }}>{user?.name}</div>
                    <div className="muted">{user?.email}</div>
                    <div className="row" style={{ gap: 6, marginTop: 6 }}>
                      <span className="chip green">{user?.provider === "google" ? "Google" : user?.provider === "facebook" ? "Facebook" : "อีเมล/รหัสผ่าน"}</span>
                      <span className="chip">{user?.role === "owner" ? "เจ้าของ" : "สมาชิก"}</span>
                    </div>
                  </div>
                </div>
                <div className="field"><label>ชื่อที่แสดง</label>
                  <input type="text" value={pname} onChange={(e) => setPname(e.target.value)} placeholder="ชื่อของคุณ" /></div>
                <div className="row" style={{ justifyContent: "flex-end", marginTop: 12 }}>
                  <button className="btn-green" onClick={saveProfile} disabled={busy}>บันทึกชื่อ</button>
                </div>
                <div className="h-px bg-line my-4" />
                <button className="btn-outline" onClick={logout}><Icon name="logout" size={16} /> ออกจากระบบ</button>
              </div>

              <div className="card">
                <h3><span className="row" style={{ gap: 8 }}><Icon name="lock" size={16} /> เปลี่ยนรหัสผ่าน</span></h3>
                {user?.provider && user.provider !== "password" ? (
                  <div className="toast warn" style={{ margin: 0 }}>บัญชีนี้เข้าสู่ระบบด้วย {user.provider === "google" ? "Google" : "Facebook"} จึงไม่มีรหัสผ่านให้เปลี่ยน</div>
                ) : (
                  <div className="stack">
                    <div><label>รหัสผ่านเดิม</label><input type="password" autoComplete="current-password" value={pwOld} onChange={(e) => setPwOld(e.target.value)} /></div>
                    <div><label>รหัสผ่านใหม่</label><input type="password" autoComplete="new-password" value={pwNew} onChange={(e) => setPwNew(e.target.value)} placeholder="อย่างน้อย 8 ตัวอักษร" /></div>
                    <div><label>ยืนยันรหัสผ่านใหม่</label><input type="password" autoComplete="new-password" value={pwConfirm} onChange={(e) => setPwConfirm(e.target.value)} /></div>
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      <button className="btn-green" onClick={savePw} disabled={busy || !pwOld || !pwNew}>เปลี่ยนรหัสผ่าน</button>
                    </div>
                  </div>
                )}
              </div>
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

      <div className="fab">
        <button className="btn-outline" onClick={() => toast("มีอะไรใหม่: ระบบ auth + OAuth + ธีม Paypers")}><Icon name="sparkles" size={15} /> มีอะไรใหม่</button>
        <button className="btn-outline" onClick={() => toast("เปิด README.md เพื่อดูคู่มือการใช้งาน")}><Icon name="list" size={15} /> คู่มือใช้งาน</button>
      </div>
    </div>
  );
}

function AdSetTable({ adsets, minRoas, onSeed }: { adsets: AdSet[]; minRoas: number; onSeed: () => void }) {
  if (adsets.length === 0) {
    return (
      <div className="empty">
        <svg className="art" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 2h9l3 3v17l-2-1.5L14 22l-2-1.5L10 22l-2-1.5L6 22z" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="9" y1="12" x2="15" y2="12" /><path d="M12 15c1.5 0 2.5-1 2.5-2.2S13.5 10.6 12 10.6 9.5 11.6 9.5 12.8 10.5 15 12 15z" />
        </svg>
        <h4>ยังไม่มี Ad Sets</h4>
        <div>เชื่อม Meta แล้วกด “Sync Meta” หรือลองข้อมูลตัวอย่างก่อน</div>
        <button className="btn-dark" style={{ marginTop: 14 }} onClick={onSeed}>เพิ่มข้อมูลตัวอย่าง</button>
      </div>
    );
  }
  return (
    <table>
      <thead><tr><th>ชื่อ</th><th>สินค้า</th><th>งบ/วัน</th><th>จ่ายแล้ว</th><th>ROAS</th><th>สถานะ</th></tr></thead>
      <tbody>
        {adsets.map((a) => (
          <tr key={a.id}><td>{a.name}</td><td>{a.product || "-"}</td>
            <td>{Number(a.daily_budget).toLocaleString()}</td><td>{Number(a.spend).toLocaleString()}</td>
            <td><span className={`pill ${a.in_learning ? "learn" : a.roas >= minRoas ? "good" : "bad"}`}>{a.in_learning ? "Learning" : a.roas.toFixed(2)}</span></td>
            <td><span className={`pill ${a.status === "ACTIVE" ? "good" : "pause"}`}>{a.status}</span></td></tr>))}
      </tbody>
    </table>
  );
}
