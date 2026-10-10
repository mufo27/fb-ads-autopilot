// ไอคอนเส้นสไตล์ Lucide/Feather (stroke=currentColor, ไม่ต้องพึ่งไลบรารี)
import type { ReactNode } from "react";
type P = { name: string; size?: number; className?: string };

const PATHS: Record<string, ReactNode> = {
  dashboard: (<><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /></>),
  target: (<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.4" /></>),
  shield: (<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />),
  list: (<><line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3.5" y1="6" x2="3.5" y2="6" /><line x1="3.5" y1="12" x2="3.5" y2="12" /><line x1="3.5" y1="18" x2="3.5" y2="18" /></>),
  key: (<><circle cx="7.5" cy="15.5" r="4.5" /><path d="M10.7 12.3 21 2" /><path d="M16 7l3 3" /></>),
  refresh: (<><path d="M21 12a9 9 0 1 1-2.6-6.4" /><path d="M21 3v5h-5" /></>),
  play: (<polygon points="6 4 20 12 6 20 6 4" />),
  power: (<><path d="M18.4 6.6a9 9 0 1 1-12.8 0" /><line x1="12" y1="2" x2="12" y2="12" /></>),
  logout: (<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></>),
  sparkles: (<><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z" /><path d="M19 15l.7 1.8L21.5 17.5l-1.8.7L19 20l-.7-1.8L16.5 17.5l1.8-.7z" /></>),
  alert: (<><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>),
  check: (<><path d="M22 11.1V12a10 10 0 1 1-5.9-9.1" /><polyline points="22 4 12 14 9 11" /></>),
  trending: (<><polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" /></>),
  box: (<><path d="M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" /><polyline points="3.3 7 12 12 20.7 7" /><line x1="12" y1="22" x2="12" y2="12" /></>),
  activity: (<polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />),
  coins: (<><circle cx="8" cy="8" r="5" /><path d="M18.1 6.6a5 5 0 1 1-6.7 6.7" /><path d="M7 6h1v4" /></>),
  chevron: (<polyline points="6 9 12 15 18 9" />),
  user: (<><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6" /></>),
  lock: (<><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>),
  mail: (<><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></>),
};

export function Icon({ name, size = 18, className }: P) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {PATHS[name] ?? null}
    </svg>
  );
}
