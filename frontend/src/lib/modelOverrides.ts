// Remembers a model override the user picked after hitting the rate-limit
// dialog, for the rest of this browser tab's session — so the very next
// run doesn't immediately hit the same wall and re-prompt.
//
// Module state, not localStorage: a page reload forgets it, the same way
// Demo Mode does — there is no server-side counterpart either way.

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
/** Server render always starts with nothing remembered. */
export const getModelOverridesServerSnapshot = (): Partial<Record<ModelTier, string>> => ({});
