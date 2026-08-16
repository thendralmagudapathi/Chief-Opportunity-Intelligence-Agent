"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { OpportunityListItem } from "@/lib/types";
import { Button, EmptyState, Panel, Pill } from "@/components/ui";

const CATEGORIES = [
  "",
  "job",
  "freelance",
  "consulting",
  "grant",
  "fellowship",
  "scholarship",
  "accelerator",
  "competition",
  "research",
  "partnership",
  "open_source",
];

export default function OpportunitiesPage() {
  const [items, setItems] = useState<OpportunityListItem[]>([]);
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("score");
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(
    async (nextCursor: string | null, append: boolean) => {
      setLoading(true);
      setError(null);
      try {
        const params: Record<string, string> = { limit: "20", sort };
        if (category) params.category = category;
        if (nextCursor) params.cursor = nextCursor;
        const page = await api.opportunities(params);
        setItems((prev) => (append ? [...prev, ...page.items] : page.items));
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    },
    [category, sort],
  );

  useEffect(() => {
    void load(null, false);
  }, [load]);

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">Opportunity explorer</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Filter and rank the corpus. Pagination is keyset-based, so results stay
          stable while discovery keeps inserting.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <Select label="Category" value={category} onChange={setCategory} options={CATEGORIES} />
        <Select
          label="Sort"
          value={sort}
          onChange={setSort}
          options={["score", "deadline", "recent"]}
        />
      </div>

      {error && (
        <div className="rounded-lg border border-[var(--color-negative)]/30 bg-[var(--color-negative)]/10 px-4 py-3 text-sm text-[var(--color-negative)]">
          {error}
        </div>
      )}

      <Panel>
        {items.length === 0 && !loading ? (
          <EmptyState
            title="No opportunities match"
            detail="The corpus is empty until the discovery sources are implemented in Phase 2. Filtering, sorting and pagination against the live database already work."
            hint="GET /api/v1/opportunities?sort=score"
          />
        ) : (
          <ul className="divide-y divide-[var(--color-edge)]">
            {items.map((item) => (
              <li key={item.id} className="py-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="truncate text-sm font-medium hover:text-[var(--color-accent)]"
                    >
                      {item.title}
                    </a>
                    <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                      {[
                        item.organization_name,
                        item.location_city,
                        item.location_country,
                        item.remote_status,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Pill>{item.category}</Pill>
                    {item.overall_score && <Pill tone="ok">{item.overall_score}</Pill>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
        {hasMore && (
          <div className="pt-4">
            <Button variant="ghost" disabled={loading} onClick={() => void load(cursor, true)}>
              {loading ? "Loading…" : "Load more"}
            </Button>
          </div>
        )}
      </Panel>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <label className="flex items-center gap-2 text-xs text-[var(--color-ink-muted)]">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-[var(--color-edge)] bg-[var(--color-panel)] px-2.5 py-1.5 text-xs text-[var(--color-ink)] outline-none"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option === "" ? "all" : option}
          </option>
        ))}
      </select>
    </label>
  );
}
