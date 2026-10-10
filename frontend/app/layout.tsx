import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FB Ads Autopilot",
  description: "ระบบยิง Facebook Ads อัตโนมัติด้วย AI + Guardrails",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body>{children}</body>
    </html>
  );
}
