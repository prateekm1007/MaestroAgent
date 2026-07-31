import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Maestro — Today",
  description:
    "Maestro is a personal intelligence product that remembers what you promised, surfaces what changed, and tells you what to do next — with provenance. Your morning view, every day.",
  keywords: [
    "Maestro",
    "Personal Intelligence",
    "Today",
    "Commitments",
    "Briefing",
    "Provenance",
  ],
  authors: [{ name: "Maestro" }],
  icons: {
    // P-2026-07-18 fix (auditor S1 finding): was pointing at
    // https://z-cdn.chatglm.cn/z-ai/static/logo.svg — a third-party CDN
    // hosted in China, left over from the Z-AI/ChatGLM starter template.
    // Replaced with a local Maestro-branded favicon (yellow circle +
    // lightning bolt, matching the MaestroMark component).
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* LATENCY FIX: preconnect to the backend API host so the browser
            establishes DNS+TCP+TLS before the first API call fires.
            Without this, the first /api/* request pays ~100-200ms of
            connection overhead. With preconnect, the connection is
            already warm by the time JS executes. */}
        <link rel="preconnect" href="https://maestroagent-production.up.railway.app" />
        <link rel="dns-prefetch" href="https://maestroagent-production.up.railway.app" />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground min-h-screen`}
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
