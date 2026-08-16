import type { Metadata } from "next";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import "./globals.css";

export const metadata: Metadata = {
  title: "Opportunity Intelligence Agent",
  description:
    "Autonomous discovery, research, qualification, scoring and recommendation of opportunities.",
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/opportunities", label: "Opportunities" },
  { href: "/goals", label: "Goals" },
  { href: "/system", label: "System" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <div className="flex min-h-screen">
          <aside className="hidden w-56 shrink-0 border-r border-[var(--color-edge)] bg-[var(--color-panel)] p-5 md:block">
            <div className="mb-8">
              <p className="text-sm font-semibold leading-tight">Opportunity</p>
              <p className="text-sm font-semibold leading-tight text-[var(--color-accent)]">
                Intelligence
              </p>
              <p className="mt-2 text-[11px] uppercase tracking-widest text-[var(--color-ink-muted)]">
                Phase 1 · foundation
              </p>
            </div>
            <nav className="space-y-1">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="block rounded-lg px-3 py-2 text-sm text-[var(--color-ink-muted)] transition hover:bg-[var(--color-panel-raised)] hover:text-[var(--color-ink)]"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <p className="mt-10 text-[11px] leading-relaxed text-[var(--color-ink-muted)]">
              Agent trace, applications and evaluation pages arrive with Phases 4 and 7.
            </p>
          </aside>
          <main className="flex-1">
            <AuthGate>{children}</AuthGate>
          </main>
        </div>
      </body>
    </html>
  );
}
