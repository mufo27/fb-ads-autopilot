"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#FFC107" d="M43.6 20.5H42V24H24v8h11.3C33.7 37.3 29.3 40 24 40c-8.8 0-16-7.2-16-16S15.2 8 24 8c4.1 0 7.8 1.6 10.6 4.1l5.7-5.7C36.5 3.1 30.6 0 24 0 10.7 0 0 10.7 0 24s10.7 24 24 24 24-10.7 24-24c0-1.2-.1-2.3-.4-3.5z"/><path fill="#FF3D00" d="M3.1 12.5l6.6 4.8C12.1 13.3 17.6 8 24 8c3.7 0 7 1.4 9.5 3.8l6.6-6.6C36 2.3 30.4 0 24 0 14 0 5.5 5.9 1.9 14.4z"/><path fill="#4CAF50" d="M24 48c6.2 0 11.8-2.4 16-6.3l-7.4-6.3C30 36.7 27.1 38 24 38c-5.2 0-9.6-3.1-11.5-7.5l-7.6 5.9C9.1 42.1 16 48 24 48z"/><path fill="#1976D2" d="M43.6 20.5H42V24H24v8h11.3c-.8 2.2-2.2 4.1-4 5.5l7.4 6.3C41.9 40.6 48 33 48 24c0-1.2-.1-2.3-.4-3.5z"/></svg>
);
const FacebookIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24"><path fill="#1877F2" d="M24 12a12 12 0 1 0-13.9 11.9v-8.4H7.9V12h2.2V9.8c0-2.2 1.3-3.4 3.3-3.4.9 0 1.9.2 1.9.2v2.1h-1.1c-1 0-1.4.7-1.4 1.4V12h2.4l-.4 3.5h-2v8.4A12 12 0 0 0 24 12z"/></svg>
);

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState({ google: false, facebook: false });

  useEffect(() => { fetch(`${API}/api/auth/oauth-providers`).then(r => r.json()).then(setProviders).catch(() => {}); }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const r = await fetch(API + path, {
        method: "POST", credentials: "include", headers: { "content-type": "application/json" },
        body: JSON.stringify(mode === "login" ? { email, password: pw } : { email, name, password: pw }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(d.detail || "เข้าสู่ระบบไม่สำเร็จ"); return; }
      router.replace("/");
    } catch { setErr("เชื่อมต่อ backend ไม่ได้"); } finally { setBusy(false); }
  }

  return (
    <div className="auth-wrap">
      <div className="login-card">
        <div className="brand" style={{ padding: 0, justifyContent: "center", marginBottom: 6 }}>
          <div className="logo" /><div><b style={{ fontSize: 17 }}>FB Ads Autopilot</b></div>
        </div>
        <div className="muted" style={{ textAlign: "center", marginBottom: 8 }}>
          {mode === "login" ? "เข้าสู่ระบบเพื่อจัดการแอดอัตโนมัติ" : "สร้างบัญชีใหม่เพื่อเริ่มใช้งาน"}
        </div>

        <div className="auth-tabs">
          <button className={mode === "login" ? "on" : ""} onClick={() => { setMode("login"); setErr(""); }}>เข้าสู่ระบบ</button>
          <button className={mode === "register" ? "on" : ""} onClick={() => { setMode("register"); setErr(""); }}>สมัครสมาชิก</button>
        </div>

        <div className="social">
          <a href={`${API}/api/auth/google/start`} style={providers.google ? {} : { opacity: .5, pointerEvents: "none" }}>
            <button type="button" className="social-btn" style={{ width: "100%" }}><GoogleIcon /> <span className="g">ดำเนินการต่อด้วย Google</span></button>
          </a>
          <a href={`${API}/api/auth/facebook/start`} style={providers.facebook ? {} : { opacity: .5, pointerEvents: "none" }}>
            <button type="button" style={{ width: "100%" }}><FacebookIcon /> <span className="f">ดำเนินการต่อด้วย Facebook</span></button>
          </a>
        </div>
        {!providers.google && !providers.facebook && (
          <div className="muted" style={{ fontSize: 12, marginTop: 8, textAlign: "center" }}>
            (ปุ่ม Google/Facebook จะใช้ได้เมื่อใส่ OAuth client id/secret ใน .env)
          </div>
        )}

        <div className="divider">หรือใช้ อีเมล &amp; รหัสผ่าน</div>

        <form onSubmit={submit} className="stack">
          {mode === "register" && (
            <div><label>ชื่อ</label><input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="เช่น Watcharapong" /></div>
          )}
          <div><label>อีเมล</label><input type="text" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></div>
          <div><label>รหัสผ่าน</label><input type="password" required value={pw} onChange={(e) => setPw(e.target.value)} placeholder={mode === "register" ? "อย่างน้อย 8 ตัวอักษร" : "••••••••"} /></div>
          {err && <div className="toast err" style={{ margin: 0 }}>{err}</div>}
          <button type="submit" className="btn-green" disabled={busy} style={{ width: "100%", marginTop: 4 }}>
            {busy ? "กำลังดำเนินการ…" : mode === "login" ? "เข้าสู่ระบบ" : "สมัครสมาชิก"}
          </button>
        </form>
      </div>
    </div>
  );
}
