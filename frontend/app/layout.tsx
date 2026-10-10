import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FB Ads Autopilot",
  description: "ระบบยิง Facebook Ads อัตโนมัติด้วย AI + Guardrails",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th">
      <body>{children}</body>
    </html>
  );
}
