"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Goal, HealthResponse, OpportunityListItem } from "@/lib/types";
import { EmptyState, Panel, Pill } from "@/components/ui";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.goals(), api.opportunities({ limit: "5" })])
      .then(([h, g, o]) => {
        setHealth(h);
        setGoals(g);
        setOpportunities(o.items);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const activeGoals = goals.filter((g) => g.status === "active");

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Top opportunities are ranked against your active objectives — not against
          each other in the abstract.
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-[var(--color-negative)]/30 bg-[var(--color-negative)]/10 px-4 py-3 text-sm text-[var(--color-negative)]">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Active objectives" value={String(activeGoals.length)} />
        <Stat label="Opportunities tracked" value={String(opportunities.length)} />
        <Stat
          label="Backend"
          value={health?.status ?? "…"}
          tone={health?.status === "ok" ? "ok" : health ? "error" : "neutral"}
        />
      </div>

      <Panel
        title="TOP OPPORTUNITIES"
        subtitle="Ranked by the deterministic scoring engine, explained by evidence."
      >
        {opportunities.length === 0 ? (
          <EmptyState
            title="No opportunities yet"
            detail="Discovery, deduplication and scoring arrive in Phase 2; the agent graph that populates this list arrives in Phase 4. The read path, ranking query and pagination are already live."
            hint="GET /api/v1/opportunities"
          />
        ) : (
          <ul className="divide-y divide-[var(--color-edge)]">
            {opportunities.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{item.title}</p>
                  <p className="mt-0.5 truncate text-xs text-[var(--color-ink-muted)]">
                    {item.organization_name ?? "Unknown organisation"} · {item.category}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {item.overall_score && <Pill>{item.overall_score}</Pill>}
                  {item.recommendation && <Pill tone="ok">{item.recommendation}</Pill>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="ACTIVE OBJECTIVES" subtitle="An opportunity's value depends on these.">
          {activeGoals.length === 0 ? (
            <EmptyState
              title="No active objectives"
              detail="Create one on the Goals page. Scoring weights are selected by the objective profile you choose."
            />
          ) : (
            <ul className="space-y-2">
              {activeGoals.map((goal) => (
                <li
                  key={goal.id}
                  className="flex items-center justify-between gap-3 rounded-lg bg-[var(--color-panel-raised)] px-3 py-2"
                >
                  <span className="truncate text-sm">{goal.title}</span>
                  <Pill>{goal.objective_profile}</Pill>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="OPPORTUNITIES YOU SHOULD IGNORE"
          subtitle="Reducing information overload is a deliverable, not a side effect."
        >
          <EmptyState
            title="Nothing suppressed yet"
            detail="Once the contrarian and decision agents run, everything the system deliberately filtered out is listed here with the reason — so suppression is auditable rather than invisible."
          />
        </Panel>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "ok" | "error" | "neutral";
}) {
  return (
    <div className="rounded-xl border border-[var(--color-edge)] bg-[var(--color-panel)] px-4 py-3">
      <p className="text-[11px] uppercase tracking-widest text-[var(--color-ink-muted)]">
        {label}
      </p>
      <div className="mt-1.5">
        {tone === "neutral" ? (
          <span className="text-lg font-semibold">{value}</span>
        ) : (
          <Pill tone={tone}>{value}</Pill>
        )}
      </div>
    </div>
  );
}
