"use client";

/**
 * Minimal auth shell for the Phase 1 skeleton.
 *
 * The token lives in localStorage, which is acceptable for a local development
 * dashboard and is explicitly on the list of things to replace with an
 * httpOnly cookie session before this is exposed beyond localhost.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, api, getToken, setToken } from "@/lib/api";
import type { User } from "@/lib/types";
import { Button, Field, Panel } from "@/components/ui";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setChecking(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, []);

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      setBusy(true);
      setError(null);
      try {
        if (mode === "register") await api.register(email, password);
        const tokens = await api.login(email, password);
        setToken(tokens.access_token);
        setUser(await api.me());
      } catch (err) {
        const problem = err instanceof ApiError ? err.problem : null;
        setError(
          problem?.errors?.[0]?.message ??
            (err instanceof Error ? err.message : "Something went wrong"),
        );
      } finally {
        setBusy(false);
      }
    },
    [email, password, mode],
  );

  if (checking) {
    return (
      <p className="p-10 text-sm text-[var(--color-ink-muted)]">Checking session…</p>
    );
  }

  if (!user) {
    return (
      <div className="mx-auto mt-24 w-full max-w-sm px-6">
        <h1 className="mb-1 text-lg font-semibold">Opportunity Intelligence</h1>
        <p className="mb-6 text-xs text-[var(--color-ink-muted)]">
          {mode === "login" ? "Sign in to continue." : "Create an account to continue."}
        </p>
        <Panel>
          <form onSubmit={submit} className="space-y-4">
            <Field
              label="Email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
            <Field
              label="Password"
              type="password"
              required
              minLength={12}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
            {mode === "register" && (
              <p className="text-[11px] text-[var(--color-ink-muted)]">
                Minimum 12 characters.
              </p>
            )}
            {error && (
              <p className="text-xs text-[var(--color-negative)]" role="alert">
                {error}
              </p>
            )}
            <div className="flex items-center justify-between pt-1">
              <button
                type="button"
                className="text-xs text-[var(--color-ink-muted)] underline-offset-4 hover:underline"
                onClick={() => {
                  setMode(mode === "login" ? "register" : "login");
                  setError(null);
                }}
              >
                {mode === "login" ? "Create an account" : "I already have an account"}
              </button>
              <Button type="submit" disabled={busy}>
                {busy ? "Working…" : mode === "login" ? "Sign in" : "Register"}
              </Button>
            </div>
          </form>
        </Panel>
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center justify-between border-b border-[var(--color-edge)] px-6 py-2.5 text-xs text-[var(--color-ink-muted)]">
        <span>{user.email}</span>
        <button
          className="underline-offset-4 hover:underline"
          onClick={() => {
            setToken(null);
            setUser(null);
          }}
        >
          Sign out
        </button>
      </div>
      {children}
    </>
  );
}
