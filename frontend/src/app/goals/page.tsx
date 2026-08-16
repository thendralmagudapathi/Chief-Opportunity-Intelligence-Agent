"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Goal, ObjectiveProfile } from "@/lib/types";
import { Button, EmptyState, Field, Panel, Pill } from "@/components/ui";

const PROFILES: ObjectiveProfile[] = [
  "career",
  "income",
  "business",
  "learning",
  "networking",
  "startup",
  "research",
];

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [title, setTitle] = useState("");
  const [profile, setProfile] = useState<ObjectiveProfile>("career");
  const [priority, setPriority] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    api
      .goals()
      .then(setGoals)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(refresh, [refresh]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createGoal({
        title,
        objective_profile: profile,
        priority,
      });
      setTitle("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create goal");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">Objectives</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          The objective profile selects the scoring weight vector. The same
          opportunity scores differently under an income objective than a career one.
        </p>
      </header>

      <Panel title="NEW OBJECTIVE">
        <form onSubmit={create} className="space-y-4">
          <Field
            label="Title"
            required
            minLength={3}
            placeholder="Move to Germany and secure an AI engineering role"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <div className="flex flex-wrap items-end gap-4">
            <label className="text-xs text-[var(--color-ink-muted)]">
              <span className="mb-1.5 block font-medium">Objective profile</span>
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value as ObjectiveProfile)}
                className="rounded-lg border border-[var(--color-edge)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)] outline-none"
              >
                {PROFILES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-[var(--color-ink-muted)]">
              <span className="mb-1.5 block font-medium">Priority (1 = highest)</span>
              <input
                type="number"
                min={1}
                max={5}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
                className="w-24 rounded-lg border border-[var(--color-edge)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none"
              />
            </label>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Create objective"}
            </Button>
          </div>
          {error && (
            <p className="text-xs text-[var(--color-negative)]" role="alert">
              {error}
            </p>
          )}
        </form>
      </Panel>

      <Panel title="OBJECTIVES">
        {goals.length === 0 ? (
          <EmptyState
            title="No objectives yet"
            detail="Opportunities cannot be scored without one; the ranking query is keyed on the active goal."
          />
        ) : (
          <ul className="divide-y divide-[var(--color-edge)]">
            {goals.map((goal) => (
              <li key={goal.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{goal.title}</p>
                  <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                    priority {goal.priority}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Pill>{goal.objective_profile}</Pill>
                  <Pill tone={goal.status === "active" ? "ok" : "neutral"}>{goal.status}</Pill>
                  <button
                    className="text-xs text-[var(--color-ink-muted)] underline-offset-4 hover:text-[var(--color-negative)] hover:underline"
                    onClick={async () => {
                      await api.deleteGoal(goal.id);
                      refresh();
                    }}
                  >
                    delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
