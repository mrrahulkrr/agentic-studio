// Remembers a model override the user picked after hitting the rate-limit
// dialog (ui.tsx::QuotaDialog), for the rest of this browser tab's session —
// so the very next run doesn't immediately hit the same wall and re-prompt.
//
// Same module-level store + useSyncExternalStore pattern lib/demo.ts's
// isDemo/subscribeDemo already uses, not a new state-management approach.
// Module state, not localStorage: a page reload forgets it, the same way
// Demo Mode does — there is no server-side counterpart either way, this is
// purely "what to send on the next /run-agent call from this tab."

import type { ModelTier } from "@/lib/content";

let overrides: Partial<Record<ModelTier, string>> = {};
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((fn) => fn());
}

/** Called after a quota-fallback retry succeeds, so future runs in this tab
 * use the picked model for that tier without being asked again. */
export function rememberModelOverride(tier: ModelTier, model: string): void {
  overrides = { ...overrides, [tier]: model };
  notify();
}

export function forgetModelOverrides(): void {
  if (Object.keys(overrides).length === 0) return;
  overrides = {};
  notify();
}

export function subscribeModelOverrides(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export const getModelOverridesSnapshot = (): Partial<Record<ModelTier, string>> => overrides;
/** Server render always starts with nothing remembered — this is per-tab
 * client state, same reasoning as lib/demo.ts's getDemoServerSnapshot. */
export const getModelOverridesServerSnapshot = (): Partial<Record<ModelTier, string>> => ({});
