import { useState, useEffect, useMemo } from "react";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RTooltip,
  BarChart, Bar, XAxis, YAxis, LineChart, Line, CartesianGrid
} from "recharts";

const API = window.location.protocol + "//" + window.location.hostname + ":8090";

// ── SVG Icons ──────────────────────────────────────────────────────────────────
const Icon = {
  Shield:    (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  Alert:     (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
  Lock:      (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>,
  Unlock:    (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>,
  Monitor:   (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>,
  Grid:      (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>,
  Settings:  (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
  Wifi:      (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 16 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/></svg>,
  Mail:      (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>,
  Activity:  (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>,
  Globe:     (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>,
  Slash:     (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>,
  Eye:       (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  Bug:       (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2l1.88 1.88M20.97 5c-.19 2.6-1.2 3.8-3.47 3.95L17 9c-.3 1.56-.63 3.42-1 5M3.03 5c.19 2.6 1.2 3.8 3.47 3.95L7 9c.3 1.56.63 3.42 1 5M9 14H8M16 14h-1M9 18H8M16 18h-1M12 2a4 4 0 0 1 4 4v1H8V6a4 4 0 0 1 4-4zM5 10H3M21 10h-2M5 18l-2 2M19 18l2 2M8 22h8"/></svg>,
  QrCode:    (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="5" y="5" width="3" height="3" fill="currentColor" stroke="none"/><rect x="16" y="5" width="3" height="3" fill="currentColor" stroke="none"/><rect x="16" y="16" width="3" height="3" fill="currentColor" stroke="none"/><rect x="5" y="16" width="3" height="3" fill="currentColor" stroke="none"/></svg>,
  Cpu:       (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>,
  WhatsApp: (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill={p.c||"currentColor"}><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z"/></svg>,
  Check:     (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>,
  X:         (p={}) => <svg width={p.s||20} height={p.s||20} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>,
  Sun:       (p={}) => <svg width={p.s||18} height={p.s||18} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>,
  Moon:      (p={}) => <svg width={p.s||18} height={p.s||18} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>,
  Menu:      (p={}) => <svg width={p.s||22} height={p.s||22} viewBox="0 0 24 24" fill="none" stroke={p.c||"currentColor"} strokeWidth="1.5" strokeLinecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>,
};

// ── Hooks ──────────────────────────────────────────────────────────────────────
function useAPI(endpoint, interval = 30000) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const go = async () => {
    if (document.hidden) return;
    try {
      const r = await fetch(`${API}${endpoint}`);
      if (!r.ok) throw new Error();
      setData(await r.json()); setError(false);
    } catch { setError(true); } finally { setLoading(false); }
  };
  useEffect(() => {
    go();
    const t = setInterval(go, interval);
    return () => clearInterval(t);
  }, [endpoint, interval]);
  return { data, loading, error, refetch: go, setData };
}

function timeAgo(dt) {
  if (!dt) return "—";
  const m = Math.floor((Date.now() - new Date(dt).getTime()) / 60000);
  if (m < 1) return "ahora";
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h`;
}

function wasSeenWithinLast24Hours(dt) {
  if (!dt) return false;
  const lastSeenAt = new Date(dt).getTime();
  if (Number.isNaN(lastSeenAt)) return false;
  return Date.now() - lastSeenAt <= 24 * 60 * 60 * 1000;
}

function devIcon(vendor = "", type = "") {
  const v = (vendor + type).toLowerCase();
  if (v.includes("apple") || v.includes("iphone") || v.includes("ipad"))
    return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M12 2c-1.5 0-3 1-3 2.5 0 .5.2 1 .5 1.5H9c-2 0-4 2-4 5 0 3.5 2 8 4 8 .8 0 1.5-.5 2-1h2c.5.5 1.2 1 2 1 2 0 4-4.5 4-8 0-3-2-5-4-5h-.5c.3-.5.5-1 .5-1.5C15 3 13.5 2 12 2z"/></svg>;
  if (v.includes("samsung") || v.includes("android"))
    return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><rect x="7" y="2" width="10" height="20" rx="2"/><circle cx="12" cy="18" r="1" fill="currentColor" stroke="none"/></svg>;
  if (v.includes("tp-link") || v.includes("cisco") || v.includes("router"))
    return <Icon.Wifi />;
  if (v.includes("intel") || v.includes("dell") || v.includes("hp") || v.includes("lenovo"))
    return <Icon.Monitor />;
  return <Icon.Cpu />;
}

// ── Atoms ──────────────────────────────────────────────────────────────────────
function Dot({ color, pulse = false }) {
  return (
    <span style={{ position:"relative", display:"inline-block", width:8, height:8, flexShrink:0 }}>
      {pulse && <span style={{ position:"absolute", inset:0, borderRadius:"50%", background:color, animation:"pulse 2s ease-in-out infinite", opacity:.8 }}/>}
      <span style={{ position:"absolute", inset:0, borderRadius:"50%", background:color }}/>
    </span>
  );
}

function SevChip({ sev }) {
  const map = { alta:"var(--red)", media:"var(--amber)", baja:"var(--teal-brt)" };
  const color = map[sev] || "var(--text3)";
  return <span style={{ fontFamily:"var(--mono)", fontSize:10, fontWeight:700, letterSpacing:".12em", textTransform:"uppercase", border:`1px solid ${color}`, borderRadius:3, padding:"2px 8px", color }}>{sev}</span>;
}

function Panel({ children, style={}, teal=false, error=false, onClick }) {
  return (
    <div className={onClick?"panel clickable-panel":"panel"} onClick={onClick}
      style={{ background:"var(--bg2)", border:`1px solid ${error?"var(--red)":teal?"var(--teal-brt)":"var(--border)"}`,
        borderRadius:8, overflow:"hidden", position:"relative",
        ...(teal?{boxShadow:"0 0 20px var(--teal-dim), inset 0 0 40px var(--teal-dim)"}:{}),
        ...(error?{boxShadow:"0 0 20px var(--red-dim)"}:{}), ...style }}>
      {teal && <div style={{ position:"absolute", top:0, left:0, right:0, height:2, background:"linear-gradient(90deg,transparent,var(--teal-brt),transparent)" }}/>}
      {children}
    </div>
  );
}

function PHead({ title, titleColor="var(--text2)", right, icon }) {
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"12px 16px", borderBottom:"1px solid var(--border)", background:"var(--bg1)" }}>
      <div style={{ display:"flex", alignItems:"center", gap:8 }}>
        {icon && <span style={{ color:titleColor, display:"flex" }}>{icon}</span>}
        <span style={{ fontFamily:"var(--mono)", fontSize:11, fontWeight:600, letterSpacing:".15em", textTransform:"uppercase", color:titleColor }}>{title}</span>
      </div>
      {right && <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text3)", background:"var(--bg3)", border:"1px solid var(--border)", borderRadius:4, padding:"3px 8px" }}>{right}</span>}
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:"var(--bg1)", border:"1px solid var(--border)", padding:"10px 14px", borderRadius:4, fontFamily:"var(--mono)", fontSize:11 }}>
      <p style={{ color:"var(--text2)", margin:"0 0 6px" }}>{label||payload[0].name}</p>
      {payload.map((e,i) => <p key={i} style={{ color:e.color||e.fill, margin:0, fontWeight:600 }}>{e.name}: {e.value}</p>)}
    </div>
  );
};

function ToggleSwitch({ checked, onChange, loading }) {
  return (
    <div onClick={loading ? undefined : onChange} style={{ width: 44, height: 24, borderRadius: 12, background: checked ? "var(--teal-brt)" : "var(--border2)", position: "relative", cursor: loading ? "wait" : "pointer", transition: "0.3s", opacity: loading ? 0.6 : 1, flexShrink: 0 }}>
      <div style={{ width: 20, height: 20, borderRadius: "50%", background: "#fff", position: "absolute", top: 2, left: checked ? 22 : 2, transition: "0.3s", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }}>
        {loading && <span style={{ width: 12, height: 12, border: "2px solid var(--teal-brt)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} />}
      </div>
    </div>
  );
}

function TimeSelect({ label, value, onChange, disabled }) {
  const [hour = "", minute = ""] = (value || "").split(":");
  const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));
  const minutes = ["00", "15", "30", "45"];

  const updatePart = (nextHour, nextMinute) => {
    if (!nextHour && !nextMinute) {
      onChange("");
      return;
    }
    if (!nextHour || !nextMinute) {
      onChange("");
      return;
    }
    onChange(`${nextHour}:${nextMinute}`);
  };

  return (
    <div style={{ padding: 10, borderRadius: 8, background: "var(--bg3)", border: "1px solid var(--border)" }}>
      <label style={{ display: "block", fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", marginBottom: 8 }}>
        {label}
      </label>
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 8, alignItems: "center" }}>
        <select
          value={hour}
          disabled={disabled}
          onChange={(e) => updatePart(e.target.value, minute)}
          style={{
            width: "100%",
            appearance: "none",
            WebkitAppearance: "none",
            MozAppearance: "none",
            background: "var(--bg1)",
            border: "1px solid rgba(13,148,136,.18)",
            borderRadius: 6,
            padding: "10px 12px",
            color: "var(--title)",
            fontFamily: "'IBM Plex Sans', sans-serif",
            fontSize: 14,
            fontWeight: 600,
            fontVariantNumeric: "tabular-nums",
            outline: "none",
            cursor: disabled ? "not-allowed" : "pointer",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,.02)"
          }}
        >
          <option value="">Hora</option>
          {hours.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
        <span style={{ fontFamily: "var(--mono)", fontSize: 16, color: "var(--text3)", fontWeight: 700 }}>:</span>
        <select
          value={minute}
          disabled={disabled}
          onChange={(e) => updatePart(hour, e.target.value)}
          style={{
            width: "100%",
            appearance: "none",
            WebkitAppearance: "none",
            MozAppearance: "none",
            background: "var(--bg1)",
            border: "1px solid rgba(13,148,136,.18)",
            borderRadius: 6,
            padding: "10px 12px",
            color: "var(--title)",
            fontFamily: "'IBM Plex Sans', sans-serif",
            fontSize: 14,
            fontWeight: 600,
            fontVariantNumeric: "tabular-nums",
            outline: "none",
            cursor: disabled ? "not-allowed" : "pointer",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,.02)"
          }}
        >
          <option value="">Min</option>
          {minutes.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

function normalizePackSchedules(packDetails, data = {}) {
  return Object.fromEntries(
    packDetails.map((pack) => {
      const schedule = data?.[pack.id] || {};
      return [pack.id, {
        start: schedule.start || "",
        end: schedule.end || "",
        enabled: Boolean(schedule.enabled),
        active_now: Boolean(schedule.active_now),
      }];
    })
  );
}

const PACK_DETAILS = [
  { id: "PACK_FAMILY", name: "Family Shield", desc: "Bloqueo de pornografía, apuestas y violencia", icon: <Icon.Shield s={20}/>, color: "var(--teal-brt)" },
  { id: "PACK_DETOX", name: "Modo Concentración", desc: "Bloquea redes sociales (TikTok, IG, FB)", icon: <Icon.Monitor s={20}/>, color: "var(--amber)" },
  { id: "PACK_PRIVACY", name: "Modo UltraConcentración", desc: "Filtro estricto de telemetría y Smart TVs", icon: <Icon.Eye s={20}/>, color: "var(--teal-brt)" },
  { id: "PACK_GAMES", name: "Filtro Anti-Juegos", desc: "Bloquea Fortnite, Roblox, Minecraft, Epic Games", icon: <Icon.Activity s={20}/>, color: "var(--red)" }
];

// ── Modales ────────────────────────────────────────────────────────────────────
function PremiumModal({ isOpen, onClose }) {
  const [step, setStep] = useState(0);
  if (!isOpen) return null;
  const slides = [
    { icon: <Icon.Slash s={32} c="#000"/>, title:"ADBLOCK DE RED", color:"var(--teal-brt)", desc:"Bloqueamos publicidad y rastreadores para todos los dispositivos de su red sin instalar nada en cada equipo." },
    { icon: <Icon.Globe s={32} c="#000"/>, title:"ANTI-PHISHING ACTIVO", color:"var(--amber)", desc:"Si alguien intenta engañarlo con una web falsa de su banco, el SafeLock corta la conexión antes de que cargue." },
    { icon: <Icon.Bug s={32} c="#000"/>,   title:"PROTECCIÓN MALWARE", color:"var(--red)", desc:"Listas de inteligencia de amenazas actualizadas. Bloqueamos dominios de malware conocidos en tiempo real." },
  ];
  const s = slides[step];
  return (
    <div style={{ position:"fixed", inset:0, zIndex:9999, display:"flex", alignItems:"center", justifyContent:"center", background:"rgba(0,0,0,0.90)", backdropFilter:"blur(4px)", padding:16 }}>
      <div className="modal-anim" style={{ background:"var(--bg2)", border:"1px solid var(--teal-brt)", borderRadius:8, width:"100%", maxWidth:540, overflow:"hidden", boxShadow:"0 0 40px var(--teal-dim)" }}>
        <div style={{ background:"var(--teal-brt)", padding:"24px 20px", textAlign:"center", position:"relative" }}>
          <button onClick={onClose} style={{ position:"absolute", top:12, right:16, background:"none", border:"none", color:"#000", cursor:"pointer", display:"flex" }}><Icon.X s={22} c="#000"/></button>
          <div style={{ display:"flex", justifyContent:"center", marginBottom:8 }}><Icon.Shield s={40} c="#000"/></div>
          <div style={{ fontFamily:"var(--mono)", fontSize:18, fontWeight:700, color:"#000", textTransform:"uppercase" }}>SafeLock Premium Shield</div>
          <div style={{ fontSize:12, color:"rgba(0,0,0,0.65)", marginTop:4 }}>Protección completa para toda su red</div>
        </div>
        <div style={{ padding:"20px 24px 0" }}>
          <div style={{ display:"grid", gridTemplateColumns:"1fr auto auto", gap:12, borderBottom:"1px solid var(--border)", paddingBottom:10, marginBottom:12, fontFamily:"var(--mono)", fontSize:10, color:"var(--text3)", textTransform:"uppercase" }}>
            <div>Característica</div>
            <div style={{ width:60, textAlign:"center" }}>Base</div>
            <div style={{ width:60, textAlign:"center", color:"var(--teal-brt)" }}>Premium</div>
          </div>
          {[
            ["Inventario en tiempo real", true, true],
            ["Sensor de intrusiones", true, true],
            ["Filtro Publicitario (AdBlock)", false, true],
            ["Bloqueo de Rastreadores", false, true],
            ["Anti-Phishing Activo", false, true],
            ["Protección contra Malware", false, true],
          ].map(([label, base, prem], i) => (
            <div key={i} style={{ display:"grid", gridTemplateColumns:"1fr auto auto", gap:12, alignItems:"center", marginBottom:10, fontSize:12, color:"var(--title)" }}>
              <div>{label}</div>
              <div style={{ width:60, textAlign:"center", color:base?"var(--teal-brt)":"var(--text4)", display:"flex", justifyContent:"center" }}>{base?<Icon.Check s={16} c="var(--teal-brt)"/>:<Icon.X s={16} c="var(--text4)"/>}</div>
              <div style={{ width:60, textAlign:"center", display:"flex", justifyContent:"center" }}>{prem?<Icon.Check s={16} c="var(--teal-brt)"/>:<Icon.X s={16} c="var(--text4)"/>}</div>
            </div>
          ))}
        </div>
        <div style={{ margin:"16px 24px 0", background:"var(--bg3)", border:`1px solid ${s.color}33`, borderRadius:6, padding:16 }}>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:8 }}>
            <span style={{ color:s.color, display:"flex" }}>{s.icon}</span>
            <div style={{ fontFamily:"var(--mono)", fontSize:12, fontWeight:700, color:s.color, letterSpacing:".1em" }}>{s.title}</div>
          </div>
          <div style={{ fontSize:12, color:"var(--text2)", lineHeight:1.6 }}>{s.desc}</div>
          <div style={{ display:"flex", justifyContent:"center", gap:6, marginTop:12 }}>
            {slides.map((_,i) => <div key={i} onClick={()=>setStep(i)} style={{ width:i===step?24:8, height:8, borderRadius:4, background:i===step?s.color:"var(--border)", cursor:"pointer", transition:"0.3s" }}/>)}
          </div>
        </div>
        <div style={{ padding:"16px 24px 24px" }}>
          <button onClick={()=>window.open("https://wa.me/50627719797?text=Hola,%20deseo%20activar%20el%20paquete%20Premium%20Shield%20en%20mi%20SafeLock.","_blank")}
            style={{ width:"100%", padding:14, background:"#25D366", color:"#000", border:"none", borderRadius:6, cursor:"pointer", fontSize:14, fontWeight:700, display:"flex", alignItems:"center", justifyContent:"center", gap:10 }}>
            <Icon.WhatsApp s={18} c="#000"/> Activar Premium por WhatsApp
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Vistas ─────────────────────────────────────────────────────────────────────
function Dashboard({ premiumActive, onOpenPremium, onGoPremium }) {
  const { data: summary, error: sumError } = useAPI("/summary", 15000);
  const { data: honeypot } = useAPI("/honeypot", 15000);
  const { data: recentBlocks } = useAPI("/pihole/recent-blocks", 15000);
  const { data: devices  } = useAPI("/devices",  30000);
  const { data: status   } = useAPI("/customer-status", 10000);

  const alerts  = honeypot?.events?.slice(0,4) || [];
  const sevMap  = { alta:"var(--red)", media:"var(--amber)", baja:"var(--teal-brt)" };
  const sevBg   = { alta:"var(--red-dim)", media:"var(--amber-dim)", baja:"transparent" };
  const hc = sumError ? "var(--red)" : "var(--teal-brt)";

  const pieData = useMemo(() => {
    if (!devices?.devices) return [];
    const c = {};
    devices.devices.forEach(d => {
      const v = (d.devVendor && d.devVendor!=="(unknown)") ? d.devVendor.split(" ")[0] : "Desconocido";
      c[v] = (c[v]||0)+1;
    });
    return Object.entries(c).map(([name,value])=>({name,value})).sort((a,b)=>b.value-a.value).slice(0,5);
  }, [devices]);

  const barData = useMemo(() => {
    const total = devices?.devices?.length || 0;
    const newC  = summary?.new_devices || 0;
    return [{ name:"Conocidos", value:total-newC, fill:"var(--teal-brt)" }, { name:"Nuevos", value:newC, fill:"var(--amber)" }];
  }, [devices, summary]);

const { data: honeypotGraph } = useAPI("/honeypot/graph", 15000);

const lineData = useMemo(() => {
  if (honeypotGraph?.graph?.length) {
    return honeypotGraph.graph;
  }
  return [0,1,2,3,4,5,6].map(h => ({ h: `-${6-h}h`, v: 0 }));
}, [honeypotGraph]);

  const pieColors = ["var(--teal-brt)","var(--amber)","var(--red)","var(--text3)","var(--border2)"];

  const services = [
    { key:"system", label:"Sistema principal" },
    { key:"network_monitor", label:"Monitor de dispositivos" },
    { key:"intrusion_sensor", label:"Sensor de intrusiones" },
    { key:"threat_blocking", label:"Bloqueo de amenazas" },
  ];

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
      {sumError && (
        <div style={{ background:"var(--red-dim)", border:"1px solid var(--red)", padding:"14px 20px", borderRadius:6, display:"flex", alignItems:"center", gap:12 }}>
          <Icon.Alert s={22} c="var(--red)"/>
          <div>
            <div style={{ color:"var(--title)", fontWeight:700, fontSize:14 }}>Conexión Perdida</div>
            <div style={{ color:"var(--text2)", fontSize:12, marginTop:2 }}>No se pudo contactar con el sensor. Verifique la conexión física.</div>
          </div>
        </div>
      )}

      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", background:sumError?"var(--red-dim)":"var(--teal-dim)", border:`1px solid ${hc}`, borderRadius:6, padding:"12px 20px" }}>
        <div style={{ display:"flex", alignItems:"center", gap:12 }}>
          <Dot color={hc} pulse={!sumError}/>
          <span style={{ fontFamily:"var(--mono)", fontSize:12, fontWeight:700, letterSpacing:".15em", color:hc }}>{sumError?"DESCONECTADO":(status?.headline || "SAFELOCK ACTIVO").toUpperCase()}</span>
          <span className="hide-mobile" style={{ fontSize:13, color:"var(--text2)", marginLeft:8 }}>— {summary?.total_devices??"0"} dispositivos en red</span>
        </div>
      </div>

      <div className="stats-grid">
        <div style={{ background:"var(--bg2)", border:"1px solid var(--border)", borderRadius:8, padding:"16px 20px", position:"relative", overflow:"hidden" }}>
          <div style={{ position:"absolute", top:0, left:0, width:4, height:"100%", background:"var(--teal-brt)", borderRadius:"8px 0 0 8px" }}/>
          <div style={{ paddingLeft:8 }}>
            <div style={{ fontFamily:"var(--mono)", fontSize:10, letterSpacing:".1em", textTransform:"uppercase", color:"var(--text3)", marginBottom:4 }}>Dispositivos en red</div>
            <div style={{ fontFamily:"var(--mono)", fontSize:32, fontWeight:400, color:"var(--title)", lineHeight:1 }}>{summary?.total_devices??"—"}</div>
          </div>
          <div style={{ height:100, marginTop:8 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData.length?pieData:[{name:"—",value:1}]} cx="50%" cy="50%" innerRadius={28} outerRadius={42} paddingAngle={3} dataKey="value" stroke="none" animationBegin={0} animationDuration={800}>
                  {(pieData.length?pieData:[{name:"—"}]).map((_,i)=><Cell key={i} fill={pieColors[i%pieColors.length]}/>)}
                </Pie>
                <RTooltip content={<CustomTooltip/>}/>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--text3)", marginTop:2, paddingLeft:8 }}>Por fabricante</div>
        </div>

        <div style={{ background:"var(--bg2)", border:"1px solid var(--border)", borderRadius:8, padding:"16px 20px", position:"relative", overflow:"hidden" }}>
          <div style={{ position:"absolute", top:0, left:0, width:4, height:"100%", background:"var(--amber)", borderRadius:"8px 0 0 8px" }}/>
          <div style={{ paddingLeft:8 }}>
            <div style={{ fontFamily:"var(--mono)", fontSize:10, letterSpacing:".1em", textTransform:"uppercase", color:"var(--text3)", marginBottom:4 }}>Nuevos hoy</div>
            <div style={{ fontFamily:"var(--mono)", fontSize:32, fontWeight:400, color:"var(--title)", lineHeight:1 }}>{summary?.new_devices??"—"}</div>
          </div>
          <div style={{ height:100, marginTop:8 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData} barCategoryGap="30%" margin={{top:4,right:4,left:-20,bottom:0}}>
                <XAxis dataKey="name" stroke="var(--text4)" tick={{fontFamily:"var(--mono)",fontSize:9}} tickLine={false} axisLine={false}/>
                <Bar dataKey="value" radius={[3,3,0,0]} animationBegin={0} animationDuration={800}>
                  {barData.map((e,i)=><Cell key={i} fill={e.fill}/>)}
                </Bar>
                <RTooltip content={<CustomTooltip/>} cursor={{fill:"var(--bg3)"}}/>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--text3)", marginTop:2, paddingLeft:8 }}>Conocidos vs nuevos</div>
        </div>

        <div style={{ background:"var(--bg2)", border:"1px solid var(--border)", borderRadius:8, padding:"16px 20px", position:"relative", overflow:"hidden" }}>
          <div style={{ position:"absolute", top:0, left:0, width:4, height:"100%", background:"var(--red)", borderRadius:"8px 0 0 8px" }}/>
          <div style={{ paddingLeft:8 }}>
            <div style={{ fontFamily:"var(--mono)", fontSize:10, letterSpacing:".1em", textTransform:"uppercase", color:"var(--text3)", marginBottom:4 }}>Intrusiones detectadas</div>
            <div style={{ fontFamily:"var(--mono)", fontSize:32, fontWeight:400, color:"var(--title)", lineHeight:1 }}>{summary?.honeypot_attempts??"—"}</div>
          </div>
          <div style={{ height:100, marginTop:8 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lineData} margin={{top:4,right:4,left:-30,bottom:0}}>
                <CartesianGrid stroke="var(--border)" vertical={false} strokeDasharray="3 3"/>
                <XAxis dataKey="h" stroke="var(--text4)" tick={{fontFamily:"var(--mono)",fontSize:9}} tickLine={false} axisLine={false}/>
                <Line type="monotone" dataKey="v" stroke="var(--red)" strokeWidth={2} dot={false} animationBegin={0} animationDuration={1000}/>
                <RTooltip content={<CustomTooltip/>}/>
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--text3)", marginTop:2, paddingLeft:8 }}>Últimas 6 horas</div>
        </div>
      </div>

      <div className="main-grid">
        <Panel>
          <PHead title="Sensor de intrusiones y bloqueos" titleColor="var(--red)" icon={<Icon.Alert s={14} c="var(--red)"/>} right={`${(honeypot?.total||0) + (recentBlocks?.total||0)} eventos`}/>
          {alerts.length===0 && (!recentBlocks?.blocks || recentBlocks.blocks.length===0) ? (
            <div style={{ padding:"40px 20px", textAlign:"center" }}>
              <div style={{ display:"flex", justifyContent:"center", marginBottom:12, color:"var(--teal-brt)" }}><Icon.Shield s={32}/></div>
              <div style={{ fontFamily:"var(--mono)", fontSize:12, color:"var(--text3)", letterSpacing:".1em" }}>Sin actividad sospechosa</div>
            </div>
          ) : (
            <>
              {alerts.map((e,i) => (
                <div key={i} style={{ display:"grid", gridTemplateColumns:"auto 1fr auto", gap:14, alignItems:"start", padding:"13px 16px", borderBottom:"1px solid var(--border)", borderLeft:`4px solid ${sevMap[e.severity]||"var(--text3)"}`, background:sevBg[e.severity]||"transparent" }}>
                  <span style={{ display:"flex", color:sevMap[e.severity], marginTop:2 }}>{e.severity==="alta"?<Icon.Alert s={16}/>:<Icon.Activity s={16}/>}</span>
                  <div>
                    <div style={{ fontSize:13, color:"var(--title)", fontWeight:500, marginBottom:4 }}>{e.description}</div>
                    <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--text2)" }}>Origen {e.src_ip} · {e.service}</div>
                  </div>
                  <div style={{ textAlign:"right" }}>
                    <SevChip sev={e.severity}/>
                    <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--text4)", marginTop:4 }}>{timeAgo(e.timestamp)}</div>
                  </div>
                </div>
              ))}
              {recentBlocks?.blocks?.length > 0 && (
                <div style={{ borderTop:"1px solid var(--border)", padding:"12px 16px", background:"var(--bg2)" }}>
                  <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--red)", textTransform:"uppercase", letterSpacing:".08em", marginBottom:8, display:"flex", alignItems:"center", gap:6 }}>
                    <Dot color="var(--red)"/> Amenazas Bloqueadas Recientemente:
                  </div>
                  <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                    {recentBlocks.blocks.slice(0, 5).map((b, idx) => (
                      <div key={idx} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", fontSize:12, padding:"4px 8px", background:"var(--bg3)", borderRadius:4, border:"1px solid var(--border)" }}>
                        <span style={{ fontFamily:"var(--mono)", color:"var(--red)" }}>🚫 {b.domain}</span>
                        <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text3)" }}>{b.client} · {timeAgo(b.timestamp)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </Panel>

        <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
          <Panel teal={premiumActive} onClick={premiumActive ? onGoPremium : onOpenPremium}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"12px 16px", borderBottom:`1px solid ${premiumActive?"var(--teal-dim)":"var(--border)"}`, background:premiumActive?"var(--teal-dim)":"var(--bg1)" }}>
              <div style={{ display:"flex", alignItems:"center", gap:8, fontFamily:"var(--mono)", fontSize:11, fontWeight:700, letterSpacing:".15em", color:premiumActive?"var(--teal-brt)":"var(--text3)" }}>
                <Icon.Shield s={14} c={premiumActive?"var(--teal-brt)":"var(--text3)"}/> SAFELOCK SHIELD
              </div>
              <span style={{ fontFamily:"var(--mono)", fontSize:9, fontWeight:700, background:premiumActive?"var(--teal-brt)":"var(--text4)", color:premiumActive?"var(--bg)":"var(--title)", borderRadius:3, padding:"3px 8px", textTransform:"uppercase" }}>{premiumActive?"PREMIUM ACTIVO":"SUSPENDIDO"}</span>
            </div>
            {premiumActive ? (
              <div style={{ padding:16 }}>
                <div style={{ fontSize:12, color:"var(--text2)", lineHeight:1.6, marginBottom:14 }}>Su red está protegida contra publicidad, phishing y malware.</div>
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                  {[[<Icon.Slash s={16}/>, "AdBlock"],[<Icon.Globe s={16}/>, "Anti-Phishing"],[<Icon.Bug s={16}/>, "Anti-Malware"],[<Icon.Eye s={16}/>, "Anti-Rastreo"]].map(([ico,lbl]) => (
                    <div key={lbl} style={{ padding:"10px 12px", borderRadius:6, background:"var(--bg3)", border:"1px solid rgba(15,95,95,.2)", display:"flex", alignItems:"center", gap:8 }}>
                      <span style={{ color:"var(--teal-brt)", display:"flex" }}>{ico}</span>
                      <span style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--teal-brt)", fontWeight:600 }}>{lbl}</span>
                    </div>
                  ))}
                </div>
                <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginTop:14, padding:"8px 12px", background:"var(--teal-dim)", border:"1px solid rgba(15,95,95,.2)", borderRadius:4 }}>
                  <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--teal-brt)" }}>Safelock shield activo</span>
                  <Dot color="var(--teal-brt)" pulse/>
                </div>
              </div>
            ) : (
              <div style={{ padding:"24px 20px", textAlign:"center", display:"flex", flexDirection:"column", alignItems:"center", gap:10 }}>
                <span style={{ color:"var(--text4)", display:"flex" }}><Icon.Lock s={36}/></span>
                <div style={{ fontFamily:"var(--mono)", fontSize:13, fontWeight:700, color:"var(--text2)" }}>Servicio Suspendido</div>
                <div style={{ fontSize:12, color:"var(--text3)", lineHeight:1.7, maxWidth:220 }}>El bloqueo de publicidad y phishing está inactivo. Toque aquí para reactivar su plan.</div>
                <button style={{ background:"#25D366", color:"#000", border:"none", borderRadius:6, padding:"10px 20px", cursor:"pointer", fontFamily:"var(--mono)", fontSize:11, fontWeight:700, letterSpacing:".1em", marginTop:4, display:"flex", alignItems:"center", gap:8 }}
                  onClick={e=>{e.stopPropagation();window.open("https://wa.me/50627719797?text=Hola,%20deseo%20reactivar%20mi%20plan%20Premium%20Shield.","_blank");}}>
                  <Icon.WhatsApp s={16} c="#000"/> Reactivar por WhatsApp
                </button>
              </div>
            )}
          </Panel>

          <Panel>
            <PHead title="Estado de SafeLock" icon={<Icon.Cpu s={14}/>}/>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, padding:12 }}>
              {services.map(({key,label}) => {
                const service = status?.services?.[key];
                const ok = service?.ok !== false;
                const displayLabel = service?.label || label;
                const stateLabel = key === "threat_blocking" && !ok ? "Premium inactivo" : ok ? "Funcionando" : "Requiere soporte";
                return (
                  <div key={key} style={{ display:"flex", alignItems:"center", gap:8, padding:"10px 12px", borderRadius:6, background:"var(--bg3)", border:`1px solid ${ok?"rgba(16,185,129,.2)":"rgba(239,68,68,.3)"}` }}>
                    <Dot color={ok?"var(--ok)":"var(--red)"}/>
                    <div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--title)" }}>{displayLabel}</div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:9, color:ok?"var(--ok)":"var(--text4)", textTransform:"uppercase", marginTop:1 }}>{stateLabel}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function DevicesView() {
  const { data, loading } = useAPI("/devices", 30000);
  const [search, setSearch] = useState("");
  const devs = useMemo(() => (
    (data?.devices || []).filter((d) => {
      const shouldShowByStatus = d.devStatus === 1 || wasSeenWithinLast24Hours(d.devLastConnection);
      if (!shouldShowByStatus) return false;
      if (!search) return true;

      const query = search.toLowerCase();
      return (
        (d.devName && d.devName.toLowerCase().includes(query)) ||
        (d.devLastIP && d.devLastIP.includes(search)) ||
        (d.devVendor && d.devVendor.toLowerCase().includes(query))
      );
    })
  ), [data, search]);
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
      <div style={{ position:"relative" }}>
        <span style={{ position:"absolute", left:14, top:"50%", transform:"translateY(-50%)", color:"var(--text3)", display:"flex" }}><Icon.Eye s={16}/></span>
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Buscar por nombre, IP o fabricante..."
          style={{ width:"100%", background:"var(--bg2)", border:"1px solid var(--border)", borderRadius:6, padding:"12px 14px 12px 40px", color:"var(--text)", fontSize:13, outline:"none", transition:"border-color .2s" }}
          onFocus={e=>e.target.style.borderColor="var(--teal-brt)"}
          onBlur={e=>e.target.style.borderColor="var(--border)"}/>
      </div>
      <Panel>
        <PHead title="Inventario Completo" icon={<Icon.Monitor s={14}/>} right={`${devs.length} dispositivos`}/>
        <div className="table-header" style={{ display:"grid", gridTemplateColumns:"30px 1fr 140px 120px 80px", gap:12, padding:"10px 16px", borderBottom:"1px solid var(--border)", background:"var(--bg1)" }}>
          {["","Dispositivo","IP","Visto","Estado"].map((h,i)=><span key={i} style={{ fontFamily:"var(--mono)", fontSize:10, fontWeight:600, color:"var(--text4)", textTransform:"uppercase" }}>{h}</span>)}
        </div>
        {loading ? <div style={{ padding:40, textAlign:"center", color:"var(--text3)", fontFamily:"var(--mono)", fontSize:12 }}>Analizando red...</div>
          : devs.length===0 ? <div style={{ padding:40, textAlign:"center", color:"var(--text3)", fontFamily:"var(--mono)", fontSize:12 }}>Sin resultados</div>
          : devs.map((d,i) => (
            <div key={i} className="table-row" style={{ display:"grid", gridTemplateColumns:"30px 1fr 140px 120px 80px", gap:12, padding:"13px 16px", borderBottom:"1px solid var(--border)", alignItems:"center", transition:"background .1s" }}
              onMouseEnter={e=>e.currentTarget.style.background="var(--bg1)"}
              onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
              <span style={{ color:"var(--text3)", display:"flex" }}>{devIcon(d.devVendor, d.devType)}</span>
              <div>
                <div style={{ fontSize:13, color:"var(--title)", fontWeight:500 }}>
                  {d.devName && d.devName!=="(unknown)" ? d.devName : (d.devMAC||"Desconocido")}
                  {d.devIsNew===1 && <span style={{ fontFamily:"var(--mono)", fontSize:8, fontWeight:700, background:"var(--amber-dim)", color:"var(--amber)", border:"1px solid var(--amber)", borderRadius:3, padding:"1px 5px", marginLeft:8, textTransform:"uppercase", verticalAlign:"middle" }}>nuevo</span>}
                </div>
                <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text3)", marginTop:3 }}>{d.devVendor||"No identificado"}</div>
                <div className="device-mobile-meta">
                  <div>
                    <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--text4)", textTransform:"uppercase", marginBottom:3 }}>IP</div>
                    <div style={{ fontFamily:"var(--mono)", fontSize:12, color:"var(--text2)", wordBreak:"break-word" }}>{d.devLastIP}</div>
                  </div>
                  <div>
                    <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--text4)", textTransform:"uppercase", marginBottom:3 }}>Visto</div>
                    <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--text3)" }}>{timeAgo(d.devLastConnection)}</div>
                  </div>
                  <div>
                    <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--text4)", textTransform:"uppercase", marginBottom:3 }}>Estado</div>
                    <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                      <Dot color={d.devStatus===1?"var(--ok)":"var(--text4)"}/>
                      <span style={{ fontFamily:"var(--mono)", fontSize:10, color:d.devStatus===1?"var(--ok)":"var(--text4)" }}>{d.devStatus===1?"online":"offline"}</span>
                    </div>
                  </div>
                </div>
              </div>
              <span className="hide-mobile" style={{ fontFamily:"var(--mono)", fontSize:12, color:"var(--text2)" }}>{d.devLastIP}</span>
              <span className="hide-mobile" style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--text3)" }}>{timeAgo(d.devLastConnection)}</span>
              <div className="hide-mobile" style={{ display:"flex", alignItems:"center", gap:6 }}>
                <Dot color={d.devStatus===1?"var(--ok)":"var(--text4)"}/>
                <span style={{ fontFamily:"var(--mono)", fontSize:10, color:d.devStatus===1?"var(--ok)":"var(--text4)" }}>{d.devStatus===1?"online":"offline"}</span>
              </div>
            </div>
          ))}
      </Panel>
    </div>
  );
}

// ── Protección Heurística (Heuristic Sentinel) ────────────────────────────────
// Estado vacío que se muestra cuando la API aún no ha respondido o hay un error.
// No contiene dispositivos ficticios para no confundir al usuario final.
const SENTINEL_EMPTY = {
  mode: "protect",
  last_run: null,
  devices: [],
};

const SENTINEL_STATE = {
  green:  { label:"Normal",             color:"var(--ok)",    bg:"color-mix(in srgb, var(--ok) 14%, transparent)" },
  yellow: { label:"Sospechoso",         color:"var(--amber)", bg:"var(--amber-dim)" },
  red:    { label:"Probable infección", color:"var(--red)",   bg:"var(--red-dim)" },
};
const SENTINEL_REASON = {
  dga:       "Dominios con nombre aleatorio (posible DGA)",
  beaconing: "Consultas a intervalos idénticos (beaconing)",
  nxdomain:  "Muchas consultas a dominios inexistentes",
  blocked:   "Consultas a sitios restringidos en listas negras",
};

function SemaforoChip({ state }) {
  const s = SENTINEL_STATE[state] || SENTINEL_STATE.green;
  return (
    <span style={{ display:"inline-flex", alignItems:"center", gap:6, fontFamily:"var(--mono)", fontSize:10, fontWeight:700, letterSpacing:".08em", textTransform:"uppercase", color:s.color, background:s.bg, border:`1px solid ${s.color}`, borderRadius:999, padding:"4px 10px", whiteSpace:"nowrap" }}>
      <Dot color={s.color} pulse={state==="red"}/> {s.label}
    </span>
  );
}

function HeuristicView() {
  const { data, loading, error, refetch, setData } = useAPI("/sentinel/status", 10000);
  const offline = error || (!loading && !data?.devices);
  const info = offline ? SENTINEL_EMPTY : (data || SENTINEL_EMPTY);
  const [modeDraft, setModeDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [msg, setMsg] = useState("");
  const [unblockingDomain, setUnblockingDomain] = useState(null);
  const [unblockedDomains, setUnblockedDomains] = useState({});

  useEffect(() => {
    if (modeDraft && data?.mode === modeDraft) {
      setModeDraft(null);
    }
  }, [data?.mode, modeDraft]);
  const mode = modeDraft ?? info.mode ?? "protect";
  const protect = mode === "protect";
  const devices = info.devices || [];
  const count = (st) => devices.filter(d => d.state === st).length;
  const alerts = devices.filter(d => d.state !== "green");

  const manualRefresh = async () => {
    setRefreshing(true);
    setMsg("");
    try {
      const r = await fetch(`${API}/sentinel/refresh`, { method: "POST" });
      if (r.ok) {
        const fresh = await r.json();
        setData(fresh);
      } else {
        await refetch();
      }
    } catch {
      await refetch();
    } finally {
      setRefreshing(false);
    }
  };

  const applyMode = async (next) => {
    setSaving(true); setMsg("");
    try {
      const r = await fetch(`${API}/sentinel/mode`, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ mode: next }) });
      if (!r.ok) throw new Error();
      setModeDraft(next);
    } catch {
      setMsg("No se pudo cambiar el modo. Intenta de nuevo.");
    } finally { setSaving(false); }
  };
  const onToggle = () => applyMode(protect ? "shadow" : "protect");

  const allowDomain = async (dom) => {
    setUnblockingDomain(dom);
    setMsg("");
    try {
      const r = await fetch(`${API}/sentinel/block`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain: dom, enabled: false }),
      });
      if (!r.ok) throw new Error();
      setUnblockedDomains(prev => ({ ...prev, [dom]: true }));
    } catch {
      setMsg(`No se pudo permitir ${dom}. Intente de nuevo.`);
    } finally {
      setUnblockingDomain(null);
    }
  };

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
      {loading && (
        <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--text3)", background:"var(--bg2)", border:"1px solid var(--border)", borderRadius:6, padding:"8px 14px" }}>
          Conectando con el motor de seguridad…
        </div>
      )}
      {!loading && offline && (
        <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--amber)", background:"var(--amber-dim)", border:"1px solid var(--amber)", borderRadius:6, padding:"8px 14px" }}>
          No se pudo conectar con el motor heurístico. Verifica que la API esté en ejecución.
        </div>
      )}

      <Panel teal={protect}>
        <div style={{ padding:"12px 18px", borderBottom:"1px solid var(--border)", display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:10 }}>
          <div style={{ display:"flex", alignItems:"center", gap:8, fontFamily:"var(--mono)", fontSize:12, fontWeight:700, color: protect ? "var(--teal-brt)" : "var(--title)" }}>
            <Icon.Bug s={16}/> PROTECCIÓN HEURÍSTICA ({protect ? "ESCUDO ACTIVO" : "MODO SOMBRA"})
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            {info.analizado_en && (
              <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text4)" }}>
                Escaneado {timeAgo(info.analizado_en)}
              </span>
            )}
            <button
              onClick={manualRefresh}
              disabled={refreshing}
              style={{
                background:"var(--bg3)",
                color:"var(--teal-brt)",
                border:"1px solid var(--teal-brt)",
                borderRadius:6,
                padding:"5px 12px",
                fontSize:11,
                fontWeight:600,
                cursor: refreshing ? "wait" : "pointer",
                display:"flex",
                alignItems:"center",
                gap:6
              }}
            >
              <Icon.Activity s={12}/> {refreshing ? "Escaneando…" : "↻ Analizar red ahora"}
            </button>
          </div>
        </div>
        <div style={{ padding:20, display:"flex", alignItems:"center", justifyContent:"space-between", gap:16, flexWrap:"wrap" }}>
          <div style={{ flex:"1 1 260px", minWidth:0 }}>
            <div style={{ fontSize:15, fontWeight:600, color:"var(--title)" }}>
              {protect ? "Protección activa" : "Modo Sombra (solo auditoría)"}
            </div>
            <div style={{ fontSize:13, color:"var(--text3)", marginTop:6, lineHeight:1.5 }}>
              {protect
                ? "Los dominios sospechosos se bloquean automáticamente para toda la red. El motor heurístico siempre analiza en segundo plano."
                : "Solo monitorea y avisa sin bloquear nada. Útil para revisar falsos positivos antes de activar la protección."}
            </div>
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <span style={{ fontFamily:"var(--mono)", fontSize:10, color:protect?"var(--text4)":"var(--teal-brt)", textTransform:"uppercase" }}>Sombra</span>
            <ToggleSwitch checked={protect} onChange={onToggle} loading={saving}/>
            <span style={{ fontFamily:"var(--mono)", fontSize:10, color:protect?"var(--teal-brt)":"var(--text4)", textTransform:"uppercase" }}>Protección</span>
          </div>
        </div>
        {msg && <div style={{ padding:"10px 20px", fontSize:12, color:"var(--red)", borderTop:"1px solid var(--border)" }}>{msg}</div>}
      </Panel>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))", gap:12 }}>
        {["green","yellow","red"].map(st => (
          <div key={st} style={{ background:"var(--bg2)", border:"1px solid var(--border)", borderRadius:8, padding:"14px 18px", position:"relative", overflow:"hidden" }}>
            <div style={{ position:"absolute", top:0, left:0, width:4, height:"100%", background:SENTINEL_STATE[st].color }}/>
            <div style={{ fontFamily:"var(--mono)", fontSize:28, color:"var(--title)", lineHeight:1 }}>{count(st)}</div>
            <div style={{ fontFamily:"var(--mono)", fontSize:10, color:SENTINEL_STATE[st].color, marginTop:6, textTransform:"uppercase", letterSpacing:".08em" }}>{SENTINEL_STATE[st].label}</div>
          </div>
        ))}
      </div>

      {alerts.length > 0 && (
        <Panel error={alerts.some(d => d.state === "red")}>
          <PHead title="Alertas de Seguridad" titleColor="var(--red)" icon={<Icon.Alert s={14} c="var(--red)"/>} right={`${alerts.length} dispositivo${alerts.length>1?"s":""}`}/>
          {alerts.map(d => {
            const detected = Array.from(new Set([...(d.dga_domains || []), ...(d.beacon_domains || []), ...(d.blocked_domains || [])]));
            return (
              <div key={d.ip} style={{ padding:"14px 18px", borderBottom:"1px solid var(--border)", fontSize:13, color:"var(--text2)" }}>
                <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", flexWrap:"wrap", gap:8 }}>
                  <div>
                    Dispositivo <span style={{ fontFamily:"var(--mono)", color:"var(--title)", fontWeight:600 }}>{d.name && d.name !== d.ip ? `${d.name} (${d.ip})` : d.ip}</span> {protect ? "intentó resolver un dominio sospechoso (bloqueado por SafeLock)" : "intentó resolver un dominio sospechoso (detectado)"}.
                  </div>
                  <SemaforoChip state={d.state}/>
                </div>
                {detected.length > 0 && (
                  <div style={{ marginTop:10, display:"flex", flexDirection:"column", gap:6 }}>
                    {detected.map(dom => {
                      const isAllowed = Boolean(unblockedDomains[dom] || (info.user_whitelist && info.user_whitelist.includes(dom)));
                      const isPending = unblockingDomain === dom;
                      return (
                        <div key={dom} style={{ display:"flex", alignItems:"center", justifyContent:"space-between", background:"var(--bg2)", padding:"6px 12px", borderRadius:6, border:"1px solid var(--border)", flexWrap:"wrap", gap:8 }}>
                          <span style={{ fontFamily:"var(--mono)", fontSize:12, color: isAllowed ? "var(--teal-brt)" : "var(--red)" }}>
                            {dom} {isAllowed ? "✓ (Permitido)" : "🚫 (Bloqueado)"}
                          </span>
                          {!isAllowed ? (
                            <button
                              disabled={isPending}
                              onClick={() => allowDomain(dom)}
                              style={{
                                background:"var(--bg3)",
                                color:"var(--teal-brt)",
                                border:"1px solid var(--teal-brt)",
                                borderRadius:4,
                                padding:"4px 10px",
                                fontSize:11,
                                fontWeight:600,
                                cursor: isPending ? "wait" : "pointer"
                              }}
                            >
                              {isPending ? "Desbloqueando…" : "Permitir / Desbloquear"}
                            </button>
                          ) : (
                            <span style={{ fontSize:11, color:"var(--teal-brt)", fontWeight:600 }}>
                              Desbloqueado permanente
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </Panel>
      )}

      {info.blocked_domains && info.blocked_domains.length > 0 && (
        <Panel>
          <PHead title="Dominios Bloqueados en Tiempo Real" titleColor="var(--red)" icon={<Icon.Shield s={14} c="var(--red)"/>} right={`${info.blocked_domains.length} activo${info.blocked_domains.length>1?"s":""}`}/>
          <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
            {info.blocked_domains.map(dom => {
              const isAllowed = Boolean(unblockedDomains[dom] || (info.user_whitelist && info.user_whitelist.includes(dom)));
              const isPending = unblockingDomain === dom;
              return (
                <div key={dom} style={{ display:"flex", alignItems:"center", justifyContent:"space-between", background:"var(--bg3)", padding:"10px 14px", borderRadius:6, border:"1px solid var(--border)", flexWrap:"wrap", gap:8 }}>
                  <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                    <Dot color="var(--red)" pulse/>
                    <span style={{ fontFamily:"var(--mono)", fontSize:13, color:"var(--title)" }}>{dom}</span>
                    <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--red)", background:"var(--red-dim)", border:"1px solid rgba(239,68,68,0.3)", padding:"2px 6px", borderRadius:3, textTransform:"uppercase" }}>Bloqueado</span>
                  </div>
                  {!isAllowed ? (
                    <button
                      disabled={isPending}
                      onClick={() => allowDomain(dom)}
                      style={{
                        background:"var(--bg2)",
                        color:"var(--teal-brt)",
                        border:"1px solid var(--teal-brt)",
                        borderRadius:4,
                        padding:"5px 12px",
                        fontSize:11,
                        fontWeight:600,
                        cursor: isPending ? "wait" : "pointer"
                      }}
                    >
                      {isPending ? "Desbloqueando…" : "Permitir / Desbloquear"}
                    </button>
                  ) : (
                    <span style={{ fontSize:11, color:"var(--teal-brt)", fontWeight:600 }}>Desbloqueado</span>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      <Panel>
        <PHead title="Semáforo por dispositivo" icon={<Icon.Monitor s={14}/>} right={`${devices.length} dispositivos`}/>
        <div style={{ padding:16, display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(270px,1fr))", gap:12 }}>
          {devices.length === 0 && (
            <div style={{ padding:32, textAlign:"center", color:"var(--text3)", fontSize:13, gridColumn:"1 / -1", display:"flex", flexDirection:"column", alignItems:"center", gap:10 }}>
              <Icon.Monitor s={32} c="var(--text4)"/>
              <div>No se detectaron dispositivos con tráfico DNS reciente en la red local aún.</div>
              <div style={{ fontSize:12, color:"var(--text4)", maxWidth:420, lineHeight:1.5 }}>
                Asegúrate de que los dispositivos estén enviando sus consultas DNS al SafeLock. Si acabas de realizar una prueba, pulsa el botón "↻ Analizar red ahora" arriba.
              </div>
            </div>
          )}
          {devices.map(d => {
            const s = SENTINEL_STATE[d.state] || SENTINEL_STATE.green;
            return (
              <div key={d.ip} style={{ background:"var(--bg3)", border:"1px solid var(--border)", borderRadius:8, padding:"14px 16px 14px 20px", position:"relative", overflow:"hidden", minWidth:0 }}>
                <div style={{ position:"absolute", top:0, left:0, width:4, height:"100%", background:s.color }}/>
                <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", gap:8, flexWrap:"wrap" }}>
                  <div style={{ minWidth:0 }}>
                    <div style={{ fontSize:14, fontWeight:600, color:"var(--title)", wordBreak:"break-word" }}>{d.name || d.mac || "Desconocido"}</div>
                    <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--text3)", marginTop:3 }}>{d.ip}</div>
                  </div>
                  <SemaforoChip state={d.state}/>
                </div>
                {d.reasons?.length > 0 && (
                  <ul style={{ margin:"12px 0 0", paddingLeft:18, fontSize:12, color:"var(--text2)", lineHeight:1.6 }}>
                    {d.reasons.map(r => <li key={r}>{SENTINEL_REASON[r] || r}</li>)}
                  </ul>
                )}
                {d.dga_domains?.length > 0 && (
                  <div style={{ marginTop:10, display:"flex", flexDirection:"column", gap:4 }}>
                    {d.dga_domains.map(dom => <span key={dom} style={{ fontFamily:"var(--mono)", fontSize:11, color:s.color, wordBreak:"break-all" }}>{dom}</span>)}
                  </div>
                )}
                {d.beacon_domains?.length > 0 && (
                  <div style={{ marginTop:8, display:"flex", flexDirection:"column", gap:4 }}>
                    <span style={{ fontSize:10, color:"var(--text4)", textTransform:"uppercase" }}>Beaconing a:</span>
                    {d.beacon_domains.map(dom => <span key={dom} style={{ fontFamily:"var(--mono)", fontSize:11, color:s.color, wordBreak:"break-all" }}>{dom}</span>)}
                  </div>
                )}
                {d.blocked_domains?.length > 0 && (
                  <div style={{ marginTop:8, display:"flex", flexDirection:"column", gap:4 }}>
                    <span style={{ fontSize:10, color:"var(--red)", textTransform:"uppercase", fontWeight:600 }}>
                      Bloqueados ({d.total_bloqueados || d.blocked_domains.length}):
                    </span>
                    {d.blocked_domains.map(dom => (
                      <span key={dom} style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--red)", wordBreak:"break-all" }}>
                        🚫 {dom}
                      </span>
                    ))}
                  </div>
                )}
                <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--text4)", marginTop:12 }}>
                  {d.queries} consultas · {Math.round((d.nxdomain_rate||0)*100)}% inexistentes
                </div>
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}

function SettingsView() {
  const { data: systemInfo } = useAPI("/system-info", 60000);
  const [email, setEmail] = useState("");
  const [freq, setFreq] = useState("semanal");
  const [configLoading, setConfigLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const loadConfig = async () => {
      setConfigLoading(true);
      setError("");

      try {
        const response = await fetch(`${API}/config`);
        const payload = await response.json();

        if (!response.ok) {
          throw new Error(payload?.detail || "No se pudo cargar la configuración.");
        }

        if (!cancelled) {
          setEmail(payload?.email || "");
          setFreq(payload?.frequency || "semanal");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "No se pudo cargar la configuración del dispositivo.");
        }
      } finally {
        if (!cancelled) {
          setConfigLoading(false);
        }
      }
    };

    loadConfig();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = async () => {
    if (saving) return;
    setSaving(true);
    setError("");
    setSaved(false);

    try {
      const response = await fetch(`${API}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          frequency: freq,
          alerts_enabled: true,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || "No se pudo guardar la configuración.");
      }

      setEmail(payload?.email || email.trim());
      setFreq(payload?.frequency || freq);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      console.error("Error sincronizando con la placa:", err);
      setError(err.message || "Error de conexión con la placa.");
    } finally {
      setSaving(false);
    }
  };

  const freqOptions = [
    { value: "diario", label: "Diario", desc: "Cada día" },
    { value: "semanal", label: "Semanal", desc: "Cada lunes" },
    { value: "quincenal", label: "Quincenal", desc: "Cada 2 semanas" },
    { value: "mensual", label: "Mensual", desc: "Primer día del mes" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="responsive-grid" style={{ gap: 16, display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Panel>
            <PHead title="Reportes por Email" titleColor="var(--teal-brt)" icon={<Icon.Mail s={14} c="var(--teal-brt)"/>}/>
            <div style={{ padding: 20 }}>
              {configLoading && (
                <div style={{ marginBottom: 16, fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase" }}>
                  Cargando configuración del dispositivo...
                </div>
              )}
              {error && (
                <div style={{ marginBottom: 16, padding: "10px 12px", borderRadius: 6, border: "1px solid rgba(220,38,38,.28)", background: "rgba(220,38,38,.12)", color: "var(--red)", fontSize: 12 }}>
                  {error}
                </div>
              )}
              <label style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", display: "block", marginBottom: 8 }}>Correo electrónico</label>
              <div style={{ position: "relative", marginBottom: 20 }}>
                <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text3)", display: "flex" }}><Icon.Mail s={16}/></span>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="admin@empresa.com" disabled={configLoading || saving}
                  style={{ width: "100%", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 6, padding: "11px 14px 11px 40px", color: "var(--text)", fontSize: 13, outline: "none" }} />
              </div>

              <label style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", display: "block", marginBottom: 10 }}>Frecuencia</label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 20 }}>
                {freqOptions.map(opt => (
                  <button key={opt.value} onClick={() => setFreq(opt.value)} disabled={configLoading || saving} style={{ padding: "12px", borderRadius: 6, border: `1px solid ${freq === opt.value ? "var(--teal-brt)" : "var(--border)"}`, background: freq === opt.value ? "var(--teal-dim)" : "var(--bg3)", cursor: configLoading || saving ? "not-allowed" : "pointer", textAlign: "left", opacity: configLoading || saving ? 0.7 : 1 }}>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: freq === opt.value ? "var(--teal-brt)" : "var(--title)" }}>{opt.label}</div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text3)" }}>{opt.desc}</div>
                  </button>
                ))}
              </div>

              <button onClick={handleSave} disabled={configLoading || saving} style={{ width: "100%", padding: 13, background: saved ? "var(--ok)" : "var(--teal-brt)", color: "#000", border: "none", borderRadius: 6, cursor: configLoading || saving ? "not-allowed" : "pointer", fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700, textTransform: "uppercase", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, opacity: configLoading || saving ? 0.7 : 1 }}>
                {saved ? <><Icon.Check s={16} c="#000"/> Guardado</> : <><Icon.Mail s={16} c="#000"/> {saving ? "Guardando..." : "Guardar configuración"}</>}
              </button>
            </div>
          </Panel>

          <Panel>
            <PHead title="Soporte Técnico" titleColor="var(--teal-brt)" icon={<Icon.Activity s={14} c="var(--teal-brt)"/>}/>
            <div style={{ padding: 20 }}>
              <div style={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 6, padding: 16, marginBottom: 16 }}>
                <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase" }}>WhatsApp</div>
                <div style={{ fontSize: 20, color: "var(--title)", fontWeight: 600 }}>+506 2771-9797</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <button onClick={() => window.open("https://wa.me/50627719797", "_blank")} style={{ width: "100%", background: "#25D366", color: "#000", border: "none", borderRadius: 6, padding: 12, cursor: "pointer", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                  <Icon.WhatsApp s={16} c="#000"/> WhatsApp
                </button>
                <button onClick={() => window.open("https://openlocksecurity.com/faq", "_blank")} style={{ width: "100%", background: "var(--bg2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: 12, cursor: "pointer", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                  <Icon.Globe s={16}/> FAQ SafeLock
                </button>
              </div>
            </div>
          </Panel>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Panel>
            <PHead title="Información del dispositivo" icon={<Icon.Cpu s={14}/>}/>
            <div style={{ padding: "8px 0" }}>
              {[
                ["Nombre", systemInfo?.hostname || "—"],
                ["Dirección local", systemInfo?.local_ip || "—"],
                ["Modelo", systemInfo?.hardware || "—"],
                ["Sistema", systemInfo?.system || "—"]
              ].map(([k, v], i, arr) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "11px 16px", borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none" }}>
                  <span style={{ fontSize: 13, color: "var(--text2)" }}>{k}</span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--title)" }}>{v}</span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <PHead title="Código QR de Acceso" icon={<Icon.QrCode s={14}/>}/>
            <div style={{ padding: "20px", display: "flex", alignItems: "center", gap: 20 }}>
              <div style={{ background: "#fff", padding: 8, borderRadius: 6 }}>
                <img src={`${API}/qr`} alt="QR" style={{ width: 90, height: 90 }} />
              </div>
              <div style={{ fontSize: 12, color: "var(--text3)", lineHeight: 1.6 }}>Escanee para abrir el portal desde su móvil.</div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

// ── Vista Premium Shield ───────────────────────────────────────────────────────
function PremiumView() {
  const { data: piData, loading } = useAPI("/pihole/stats", 10000);
  
  // ── ESTADOS PARA LOS PACKS DE BLOQUEO ──
  const [packs, setPacks] = useState({});
  const [toggling, setToggling] = useState(null);
  const [schedules, setSchedules] = useState({});
  const [scheduleDrafts, setScheduleDrafts] = useState({});
  const [scheduleSaving, setScheduleSaving] = useState({});
  const [scheduleStatus, setScheduleStatus] = useState({});
  const [scheduleOpen, setScheduleOpen] = useState({});

  useEffect(() => {
    fetch(`${API}/pihole/packs`)
      .then(res => res.json())
      .then(data => setPacks(data))
      .catch(console.error);
    fetch(`${API}/pihole/packs/schedules`)
      .then(res => res.json())
      .then(data => {
        const normalized = normalizePackSchedules(PACK_DETAILS, data);
        setSchedules(normalized);
        setScheduleDrafts(normalized);
      })
      .catch(console.error);
  }, []);

  const handleTogglePack = async (packId) => {
    if (toggling) return; // Evita clics múltiples
    setToggling(packId);
    const currentStatus = packs[packId] || false;
    
    try {
      const res = await fetch(`${API}/pihole/packs/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pack: packId, enabled: !currentStatus })
      });
      const result = await res.json();
      if (result.success) {
        setPacks(prev => ({ ...prev, [packId]: !currentStatus }));
        setSchedules(prev => ({
          ...prev,
          [packId]: { ...(prev[packId] || {}), active_now: !currentStatus }
        }));
        setScheduleDrafts(prev => ({
          ...prev,
          [packId]: { ...(prev[packId] || {}), active_now: !currentStatus }
        }));
      }
    } catch (err) {
      console.error("Error cambiando el pack", err);
    }
    setToggling(null);
  };

  const handleScheduleChange = (packId, field, value) => {
    setScheduleDrafts(prev => ({
      ...prev,
      [packId]: {
        ...(prev[packId] || { start: "", end: "", enabled: false, active_now: false }),
        [field]: value,
        enabled: Boolean(
          (field === "start" ? value : prev[packId]?.start) &&
          (field === "end" ? value : prev[packId]?.end)
        ),
      }
    }));
    setScheduleStatus(prev => ({ ...prev, [packId]: null }));
  };

  const toggleScheduleOpen = (packId) => {
    setScheduleOpen(prev => ({ [packId]: !prev[packId] }));
  };

  const handleClearSchedule = (packId) => {
    const cleared = { start: "", end: "", enabled: false, active_now: schedules[packId]?.active_now || false };
    setScheduleDrafts(prev => ({ ...prev, [packId]: cleared }));
    setScheduleStatus(prev => ({ ...prev, [packId]: null }));
  };

  const handleSaveSchedule = async (packId) => {
    const draft = scheduleDrafts[packId] || { start: "", end: "", enabled: false };

    if ((draft.start && !draft.end) || (!draft.start && draft.end)) {
      setScheduleStatus(prev => ({ ...prev, [packId]: { type: "error", text: "Complete ambas horas o limpie el horario." } }));
      return;
    }

    setScheduleSaving(prev => ({ ...prev, [packId]: true }));
    setScheduleStatus(prev => ({ ...prev, [packId]: null }));

    try {
      const res = await fetch(`${API}/pihole/packs/schedules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pack: packId,
          start: draft.start || "",
          end: draft.end || "",
          enabled: Boolean(draft.start && draft.end),
        }),
      });
      const result = await res.json();
      if (!result.success) {
        throw new Error(result.error || "No se pudo guardar el horario");
      }

      const nextSchedule = {
        ...(result.schedule || { start: "", end: "", enabled: false }),
        active_now: packs[packId] || false,
      };
      setSchedules(prev => ({ ...prev, [packId]: nextSchedule }));
      setScheduleDrafts(prev => ({ ...prev, [packId]: nextSchedule }));
      setScheduleStatus(prev => ({ ...prev, [packId]: { type: "ok", text: "Guardado" } }));
    } catch (err) {
      setScheduleStatus(prev => ({ ...prev, [packId]: { type: "error", text: err.message || "Error al guardar" } }));
    }

    setScheduleSaving(prev => ({ ...prev, [packId]: false }));
  };

  const getScheduleLabel = (packId) => {
    const schedule = schedules[packId];
    if (schedule?.enabled && schedule.start && schedule.end) {
      return `Activo de ${schedule.start} a ${schedule.end}`;
    }
    return "Sin horario configurado";
  };

  const getScheduleAccent = (packId) => {
    const draft = scheduleDrafts[packId] || {};
    const hasWindow = Boolean(draft.start && draft.end);
    const status = scheduleStatus[packId];

    if (status?.type === "error") {
      return { color: "var(--red)", bg: "var(--red-dim)", border: "rgba(220,38,38,.24)" };
    }
    if (hasWindow) {
      return { color: "var(--teal-brt)", bg: "var(--teal-dim)", border: "rgba(13,148,136,.22)" };
    }
    return { color: "var(--text3)", bg: "var(--bg1)", border: "var(--border)" };
  };

  const getDraftScheduleLabel = (packId) => {
    const draft = scheduleDrafts[packId] || {};
    if (draft.start && draft.end) {
      return `${draft.start} - ${draft.end}`;
    }
    if (draft.start || draft.end) {
      return "Horario incompleto";
    }
    return "Sin horario";
  };

  const modules = [
    { name: "Filtro AdBlock", desc: "Bloqueo de publicidad invasiva", icon: <Icon.Slash s={20}/>, color: "var(--teal-brt)" },
    { name: "Anti-Rastreo", desc: "Bloqueo de telemetría y trackers", icon: <Icon.Eye s={20}/>, color: "var(--teal-brt)" },
    { name: "Anti-Phishing", desc: "Protección contra webs falsas", icon: <Icon.Globe s={20}/>, color: "var(--amber)" },
    { name: "Motor Anti-Malware", desc: "Bloqueo de dominios maliciosos", icon: <Icon.Bug s={20}/>, color: "var(--red)" },
  ];

  if (loading && !piData) return <div style={{padding:40, textAlign:"center", color:"var(--text3)", fontFamily:"var(--mono)"}}>Sincronizando con Escudo de Red...</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, background: "var(--teal-dim)", border: "1px solid var(--teal-brt)", borderRadius: 8, padding: "20px 24px", boxShadow: "0 0 30px var(--teal-dim)" }}>
        <Icon.Shield s={40} c="var(--teal-brt)" />
        <div>
          <h2 style={{ margin: 0, color: "var(--teal-brt)", fontFamily: "var(--mono)", textTransform: "uppercase", fontSize: 20, letterSpacing: ".05em" }}>SafeLock Premium Shield</h2>
          <div style={{ color: "var(--text2)", fontSize: 13, marginTop: 4 }}>Datos reales de filtrado DNS. Suscripción activa.</div>
        </div>
      </div>

      <div className="stats-grid">
        <Panel style={{ padding: "20px", borderLeft: "4px solid var(--teal-brt)" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", marginBottom: 8 }}>Tráfico Analizado (24h)</div>
          <div style={{ fontSize: 36, fontFamily: "var(--mono)", color: "var(--title)", lineHeight: 1 }}>{piData?.dns_queries_today?.toLocaleString() || "0"}</div>
        </Panel>
        
        <Panel style={{ padding: "20px", borderLeft: "4px solid var(--red)" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", marginBottom: 8 }}>Bloqueados</div>
          <div style={{ fontSize: 36, fontFamily: "var(--mono)", color: "var(--red)", lineHeight: 1 }}>{piData?.ads_blocked_today?.toLocaleString() || "0"}</div>
        </Panel>

        <Panel style={{ padding: "20px", borderLeft: "4px solid var(--amber)" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", marginBottom: 8 }}>Efectividad</div>
          <div style={{ fontSize: 36, fontFamily: "var(--mono)", color: "var(--amber)", lineHeight: 1 }}>{piData?.ads_percentage_today || "0"}%</div>
        </Panel>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="premium-top-grid">
          <Panel>
            <PHead title="Actividad de Bloqueo Real" icon={<Icon.Activity s={14}/>} />
            <div style={{ height: 180, padding: "14px 16px 8px 0" }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={piData?.graph || []}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="time" stroke="var(--text4)" tick={{fontSize: 10, fontFamily: "var(--mono)"}} axisLine={false} tickLine={false} />
                  <YAxis stroke="var(--text4)" tick={{fontSize: 10, fontFamily: "var(--mono)"}} axisLine={false} tickLine={false} domain={[0, 'auto']} tickCount={5} />
                  <RTooltip content={<CustomTooltip/>} cursor={{fill: "var(--bg3)"}} />
                  <Bar dataKey="peticiones" name="Peticiones" fill="var(--teal-dim)" radius={[2,2,0,0]} />
                  <Bar dataKey="bloqueado" name="Bloqueadas" fill="var(--red)" radius={[2,2,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel>
            <PHead title="Estado de Motores Base" icon={<Icon.Cpu s={14}/>} />
            <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
              {modules.map((m, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 8 }}>
                  <div style={{ padding: 8, background: "var(--bg1)", borderRadius: 6, color: m.color, display: "flex" }}>{m.icon}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--title)" }}>{m.name}</div>
                    <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{m.desc}</div>
                  </div>
                  <Dot color="var(--ok)" pulse />
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <Panel>
            <PHead title="Control de Red Avanzado" titleColor="var(--amber)" icon={<Icon.Settings s={14} c="var(--amber)"/>} />
            <div className="premium-control-grid" style={{ padding: 16, display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
              {PACK_DETAILS.map((pack) => (
                <div key={pack.id} style={{ display: "flex", flexDirection: "column", gap: 12, padding: "12px", background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ padding: 8, background: "var(--bg1)", borderRadius: 6, color: pack.color, display: "flex" }}>{pack.icon}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--title)" }}>{pack.name}</div>
                      <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{pack.desc}</div>
                    </div>
                    <ToggleSwitch 
                      checked={packs[pack.id]} 
                      loading={toggling === pack.id} 
                      onChange={() => handleTogglePack(pack.id)} 
                    />
                  </div>

                  <div style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                    padding: 14,
                    borderRadius: 8,
                    background: `linear-gradient(180deg, ${getScheduleAccent(pack.id).bg}, var(--bg2))`,
                    border: `1px solid ${getScheduleAccent(pack.id).border}`,
                    boxShadow: scheduleDrafts[pack.id]?.start && scheduleDrafts[pack.id]?.end ? "inset 0 1px 0 rgba(255,255,255,.03)" : "none"
                  }}>
                    <button
                      onClick={() => toggleScheduleOpen(pack.id)}
                      style={{
                        width: "100%",
                        display: "flex",
                        flexWrap: "wrap",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 10,
                        padding: 0,
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                        textAlign: "left"
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                        <Dot color={getScheduleAccent(pack.id).color} pulse={Boolean(scheduleDrafts[pack.id]?.start && scheduleDrafts[pack.id]?.end)} />
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: ".12em", textTransform: "uppercase", color: getScheduleAccent(pack.id).color }}>
                            Ventana Horaria
                          </div>
                          <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {getScheduleLabel(pack.id)}
                          </div>
                        </div>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                        <div style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                          color: scheduleDrafts[pack.id]?.start && scheduleDrafts[pack.id]?.end ? "var(--teal-brt)" : "var(--text3)",
                          background: scheduleDrafts[pack.id]?.start && scheduleDrafts[pack.id]?.end ? "rgba(13,148,136,.12)" : "var(--bg3)",
                          border: `1px solid ${scheduleDrafts[pack.id]?.start && scheduleDrafts[pack.id]?.end ? "rgba(13,148,136,.24)" : "var(--border)"}`,
                          borderRadius: 999,
                          padding: "5px 10px",
                          letterSpacing: ".06em"
                        }}>
                          {getDraftScheduleLabel(pack.id)}
                        </div>
                        <span style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: 28,
                          height: 28,
                          borderRadius: "50%",
                          background: "var(--bg3)",
                          border: "1px solid var(--border)",
                          color: scheduleOpen[pack.id] ? "var(--teal-brt)" : "var(--text3)",
                          transform: scheduleOpen[pack.id] ? "rotate(180deg)" : "rotate(0deg)",
                          transition: "transform .2s ease, color .2s ease"
                        }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="6 9 12 15 18 9" />
                          </svg>
                        </span>
                      </div>
                    </button>

                    {scheduleStatus[pack.id] && (
                      <div>
                        <span style={{
                          display: "inline-flex",
                          fontFamily: "var(--mono)",
                          fontSize: 10,
                          fontWeight: 700,
                          color: scheduleStatus[pack.id].type === "ok" ? "var(--ok)" : "var(--red)",
                          border: `1px solid ${scheduleStatus[pack.id].type === "ok" ? "rgba(5,150,105,.25)" : "rgba(220,38,38,.25)"}`,
                          background: scheduleStatus[pack.id].type === "ok" ? "rgba(5,150,105,.10)" : "rgba(220,38,38,.10)",
                          borderRadius: 999,
                          padding: "4px 9px",
                          textTransform: "uppercase",
                          letterSpacing: ".08em"
                        }}>
                          {scheduleStatus[pack.id].text}
                        </span>
                      </div>
                    )}

                    {scheduleOpen[pack.id] && (
                      <>
                        <div style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                          gap: 8
                        }}>
                          <div style={{
                            padding: "10px 12px",
                            borderRadius: 8,
                            background: "var(--bg3)",
                            border: "1px solid var(--border)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 8
                          }}>
                            <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".1em" }}>
                              Desde
                            </span>
                            <span style={{ fontSize: 15, fontWeight: 600, color: "var(--title)", fontVariantNumeric: "tabular-nums" }}>
                              {scheduleDrafts[pack.id]?.start || "--:--"}
                            </span>
                          </div>
                          <div style={{
                            padding: "10px 12px",
                            borderRadius: 8,
                            background: "var(--bg3)",
                            border: "1px solid var(--border)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 8
                          }}>
                            <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".1em" }}>
                              Hasta
                            </span>
                            <span style={{ fontSize: 15, fontWeight: 600, color: "var(--title)", fontVariantNumeric: "tabular-nums" }}>
                              {scheduleDrafts[pack.id]?.end || "--:--"}
                            </span>
                          </div>
                        </div>

                        <div style={{
                          position: "relative",
                          height: 10,
                          borderRadius: 999,
                          background: "var(--bg3)",
                          border: "1px solid var(--border)",
                          overflow: "hidden"
                        }}>
                          <div style={{
                            position: "absolute",
                            inset: 1,
                            borderRadius: 999,
                            background: scheduleDrafts[pack.id]?.start && scheduleDrafts[pack.id]?.end
                              ? "linear-gradient(90deg, rgba(13,148,136,.18), rgba(13,148,136,.45), rgba(13,148,136,.18))"
                              : "transparent"
                          }} />
                        </div>

                        <div className="schedule-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10 }}>
                          <TimeSelect
                            label="Desde"
                            value={scheduleDrafts[pack.id]?.start || ""}
                            onChange={(value) => handleScheduleChange(pack.id, "start", value)}
                            disabled={Boolean(scheduleSaving[pack.id])}
                          />
                          <TimeSelect
                            label="Hasta"
                            value={scheduleDrafts[pack.id]?.end || ""}
                            onChange={(value) => handleScheduleChange(pack.id, "end", value)}
                            disabled={Boolean(scheduleSaving[pack.id])}
                          />
                        </div>

                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                          <button
                            onClick={() => handleSaveSchedule(pack.id)}
                            disabled={Boolean(scheduleSaving[pack.id])}
                            style={{
                              minWidth: 120,
                              height: 38,
                              padding: "0 14px",
                              background: "linear-gradient(135deg, var(--teal), var(--teal-brt))",
                              color: "#031311",
                              border: "none",
                              borderRadius: 999,
                              cursor: scheduleSaving[pack.id] ? "wait" : "pointer",
                              fontFamily: "var(--mono)",
                              fontSize: 11,
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: ".08em",
                              boxShadow: "0 8px 18px rgba(13,148,136,.18)"
                            }}
                          >
                            {scheduleSaving[pack.id] ? "Guardando" : "Guardar Horario"}
                          </button>
                          <button
                            onClick={() => handleClearSchedule(pack.id)}
                            disabled={Boolean(scheduleSaving[pack.id])}
                            style={{
                              height: 38,
                              padding: "0 14px",
                              background: "var(--bg3)",
                              color: "var(--text2)",
                              border: "1px solid var(--border)",
                              borderRadius: 999,
                              cursor: scheduleSaving[pack.id] ? "wait" : "pointer",
                              fontFamily: "var(--mono)",
                              fontSize: 11,
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: ".08em"
                            }}
                          >
                            Limpiar
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
      </div>
    </div>
  );
}

export default function App() {
  const [tab, setTab]       = useState("dashboard");
  const [menuOpen, setMenu] = useState(false);
  const [showP, setShowP]   = useState(false);
  const [theme, setTheme]   = useState("dark");
  const { data: statusData }= useAPI("/customer-status", 10000);
  const premiumActive = statusData?.premium_active ?? true;

  const navItems = [
    { id:"dashboard", label:"Dashboard", icon:<Icon.Grid/> },
    { id:"devices",   label:"Mi Red",    icon:<Icon.Monitor/> },
    { id:"heuristic", label:"Heurística", icon:<Icon.Bug/> },
    { id:"settings",  label:"Soporte",   icon:<Icon.Settings/> },
  ];

  return (
    <div className="app-container" data-theme={theme}>
      <PremiumModal isOpen={showP} onClose={()=>setShowP(false)}/>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
        :root {
          --bg:#000000; --bg1:#08090A; --bg2:#121417; --bg3:#1A1D21;
          --border:#333333; --border2:#555555;
          --teal:#0F5F5F; --teal-brt:#29B5B5; --teal-dim:rgba(41,181,181,.12);
          --text:#FFFFFF; --text2:#D1D5DB; --text3:#9CA3AF; --text4:#6B7280;
          --title:#FFFFFF; --red:#EF4444; --red-dim:rgba(239,68,68,.15);
          --amber:#F59E0B; --amber-dim:rgba(245,158,11,.15); --ok:#10B981;
          --mono:'IBM Plex Mono',monospace;
        }
        [data-theme="light"] {
          --bg:#F3F4F6; --bg1:#FFFFFF; --bg2:#FFFFFF; --bg3:#F9FAFB;
          --border:#E5E7EB; --border2:#D1D5DB;
          --teal:#0F5F5F; --teal-brt:#0D9488; --teal-dim:rgba(13,148,136,.10);
          --text:#111827; --text2:#374151; --text3:#6B7280; --text4:#9CA3AF;
          --title:#111827; --red:#DC2626; --red-dim:rgba(220,38,38,.10);
          --amber:#D97706; --amber-dim:rgba(217,119,6,.10); --ok:#059669;
        }
        html,body{margin:0;padding:0;height:100vh;width:100vw;background:var(--bg) !important;color:var(--text);font-family:'IBM Plex Sans',sans-serif;overflow:hidden;transition:background .3s}
        *,*::before,*::after{box-sizing:border-box}
        .app-container{display:flex;height:100vh;width:100vw;overflow:hidden}
        .sidebar{width:240px;background:var(--bg1);border-right:1px solid var(--border);display:flex;flex-direction:column;transition:transform .3s;z-index:100;flex-shrink:0}
        .main-content{flex:1;display:flex;flex-direction:column;overflow:hidden}
        .topbar{height:60px;background:var(--bg1);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 20px;justify-content:space-between;flex-shrink:0}
        .scroll-area{flex:1;overflow-y:auto;padding:24px;background:var(--bg)}
        .stats-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
        .main-grid{display:grid;grid-template-columns:1fr 310px;gap:16px;margin-top:16px}
        .premium-top-grid{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:16px}
        .responsive-grid{display:grid;grid-template-columns:1fr 1fr}
        .panel{transition:border-color .2s}
        .clickable-panel{cursor:pointer;transition:transform .2s,border-color .2s,box-shadow .2s !important}
        .clickable-panel:hover{transform:translateY(-2px);border-color:var(--teal-brt) !important}
        .hamburger{display:none;background:none;border:none;color:var(--text);cursor:pointer;padding:4px;line-height:0}
        .hide-mobile{display:block}
        .device-mobile-meta{display:none}
        .sidebar-brand{min-height:84px;display:flex;align-items:center;gap:14px;padding:14px 18px;border-bottom:1px solid var(--border);flex-shrink:0;background:linear-gradient(180deg,var(--bg1),rgba(41,181,181,.04))}
        .sidebar-logo-wrap{width:52px;height:52px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,rgba(41,181,181,.14),rgba(41,181,181,.04));border:1px solid rgba(41,181,181,.2);box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 10px 24px rgba(0,0,0,.18);flex-shrink:0}
        .sidebar-logo{height:30px;width:auto;display:block;filter:drop-shadow(0 6px 12px rgba(0,0,0,.18))}
        .sidebar-brand-copy{display:flex;flex-direction:column;min-width:0}
        .sidebar-brand-title{font-family:var(--mono);font-size:20px;line-height:1;letter-spacing:.12em;font-weight:700;color:var(--title);text-transform:uppercase}
        .sidebar-brand-subtitle{margin-top:6px;font-family:'IBM Plex Sans',sans-serif;font-size:12px;line-height:1;color:var(--text3);letter-spacing:.04em}
        .sidebar-brand-subtitle strong{color:var(--teal-brt);font-weight:600}
        .theme-btn{background:var(--bg2);border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:6px;cursor:pointer;line-height:0;transition:.2s;display:flex;align-items:center}
        .theme-btn:hover{border-color:var(--teal-brt)}
        ::-webkit-scrollbar{width:4px}
        ::-webkit-scrollbar-track{background:transparent}
        ::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
        @keyframes pulse{0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(41,181,181,.3)}50%{opacity:.7;box-shadow:0 0 0 5px transparent}}
        @keyframes popIn{from{opacity:0;transform:scale(.95) translateY(10px)}to{opacity:1;transform:scale(1) translateY(0)}}
        @keyframes spin{to{transform:rotate(360deg)}}
        .modal-anim{animation:popIn .3s cubic-bezier(.16,1,.3,1) forwards}
        @media(max-width:900px){
          .stats-grid{grid-template-columns:1fr}
          .main-grid{grid-template-columns:1fr}
          .premium-top-grid{grid-template-columns:1fr}
          .premium-control-grid{grid-template-columns:1fr !important}
          .responsive-grid{grid-template-columns:1fr !important}
          .table-header{display:none !important}
          .table-row{grid-template-columns:30px 1fr !important}
          .hide-mobile{display:none !important}
          .device-mobile-meta{display:flex;flex-direction:column;gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}
        }
        @media(max-width:768px){
          .sidebar{position:fixed;height:100%;transform:translateX(-100%)}
          .sidebar.open{transform:translateX(0);box-shadow:4px 0 20px rgba(0,0,0,.5)}
          .sidebar-brand{min-height:76px;padding:12px 16px}
          .sidebar-logo-wrap{width:46px;height:46px;border-radius:12px}
          .sidebar-logo{height:24px}
          .sidebar-brand-title{font-size:18px}
          .sidebar-brand-subtitle{font-size:11px}
          .hamburger{display:flex}
          .scroll-area{padding:16px}
        }
      `}</style>

      <aside className={`sidebar ${menuOpen?"open":""}`}>
        <div className="sidebar-brand">
          <div className="sidebar-logo-wrap">
            <img src="/safelock-logo.svg" alt="SafeLock" className="sidebar-logo" />
          </div>
          <div className="sidebar-brand-copy">
            <div className="sidebar-brand-title">SafeLock</div>
            <div className="sidebar-brand-subtitle">by <strong>OpenLock</strong></div>
          </div>
        </div>
        <div style={{ padding:"20px 12px", display:"flex", flexDirection:"column", gap:4 }}>
          <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--text4)", paddingLeft:12, marginBottom:6, letterSpacing:".12em", textTransform:"uppercase" }}>General</div>
          {navItems.map(t => (
            <button key={t.id} onClick={()=>{setTab(t.id);setMenu(false);}} style={{ display:"flex", alignItems:"center", gap:12, padding:"12px 16px", borderRadius:6, width:"100%", background:tab===t.id?"var(--teal-dim)":"transparent", color:tab===t.id?"var(--teal-brt)":"var(--text2)", border:"none", cursor:"pointer", textAlign:"left", fontSize:14, fontWeight:500, transition:"all .15s" }}>
              <span style={{ display:"flex", color:"inherit" }}>{t.icon}</span> {t.label}
            </button>
          ))}
        </div>
        
        <div style={{ marginTop:"auto", padding:"16px 12px", borderTop:"1px solid var(--border)" }}>
          {premiumActive ? (
            <button onClick={()=>{setTab("premium"); setMenu(false);}} style={{ width:"100%", padding:16, background:"var(--teal-dim)", color:"var(--teal-brt)", border:"1px solid var(--teal-brt)", borderRadius:8, cursor:"pointer", fontFamily:"var(--mono)", fontSize:12, fontWeight:700, letterSpacing:".1em", textTransform:"uppercase", display:"flex", alignItems:"center", justifyContent:"center", gap:10 }}>
              <Icon.Shield s={18} c="var(--teal-brt)"/> Panel Premium
            </button>
          ) : (
            <button onClick={()=>setShowP(true)} style={{ width:"100%", padding:16, background:"linear-gradient(135deg,var(--teal),var(--teal-brt))", color:"#000", border:"none", borderRadius:8, cursor:"pointer", fontFamily:"var(--mono)", fontSize:12, fontWeight:700, letterSpacing:".1em", textTransform:"uppercase", display:"flex", alignItems:"center", justifyContent:"center", gap:10 }}>
              <Icon.Shield s={18} c="#000"/> Premium Shield
            </button>
          )}
        </div>
      </aside>

      {menuOpen && <div onClick={()=>setMenu(false)} style={{ position:"fixed", inset:0, background:"rgba(0,0,0,.6)", zIndex:90 }}/>}

      <div className="main-content">
        <header className="topbar">
          <div style={{ display:"flex", alignItems:"center", gap:14 }}>
            <button className="hamburger" onClick={()=>setMenu(true)}><Icon.Menu/></button>
            <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--teal-brt)", display:"flex", alignItems:"center", gap:8, fontWeight:600, letterSpacing:".12em" }}>
              <Dot color="var(--teal-brt)" pulse/> {(statusData?.headline || "SafeLock activo").toUpperCase()}
            </div>
          </div>
          <button className="theme-btn" onClick={()=>setTheme(t=>t==="dark"?"light":"dark")}>
            {theme==="dark"?<Icon.Sun/>:<Icon.Moon/>}
          </button>
        </header>
        <main className="scroll-area">
          {tab==="dashboard" && <Dashboard premiumActive={premiumActive} onOpenPremium={()=>setShowP(true)} onGoPremium={()=>setTab("premium")}/>}
          {tab==="devices"   && <DevicesView/>}
          {tab==="heuristic" && <HeuristicView/>}
          {tab==="settings"  && <SettingsView/>}
          {tab==="premium"   && <PremiumView/>}
        </main>
      </div>
    </div>
  );
}
