// Developer-only: reference view of each quality tier's shipped default and
// approved alternatives. Gated the same way every other admin-only panel
// is — not by a check of its own (it makes no backend call to gate; it
// renders from lib/content.ts's mirrored constants only), but by living
// under apps/admin/components/ and only ever being rendered from
// apps/admin/app/page.tsx, which already refuses the whole app shell to
// anything but a role === "developer" session before any tab is reachable.
// Never imported into apps/client.
//
// Read-only by design, like DatabasePanel started out: changing a tier's
// default means setting its FAST_MODEL/STANDARD_MODEL/QUALITY_MODEL env var
// and redeploying (see CLAUDE.md), not a control here. No backend endpoint
// exists to persist a live change, and the approved design deliberately
// didn't ask for one — a redeploy-to-change cost is acceptable for a
// decision framed as "until further notice," and building live-editable
// infrastructure ahead of any evidence that tier defaults change often is
// exactly the kind of premature complexity worth not adding.
"use client";

import { Badge, Card, PanelIntro } from "@/components/ui";
import { TIER_CANDIDATES, TIER_DEFAULT_MODELS, TIER_LABELS, type ModelTier } from "@/lib/content";

const TIER_ORDER: ModelTier[] = ["FAST", "STANDARD", "QUALITY"];

export default function ModelsPanel() {
  return (
    <div className="space-y-6">
      <PanelIntro eyebrow="Access" title="Models">
        Which Gemini model each quality tier uses by default, and what a run falls back to if that
        model hits its free usage limit. Shown here for reference — changing a tier&apos;s default
        means setting its environment variable and redeploying, not a switch on this screen.
      </PanelIntro>

      {TIER_ORDER.map((tier) => (
        <Card key={tier} className="space-y-4">
          <div>
            <h3 className="font-semibold text-ink-50">{TIER_LABELS[tier]}</h3>
            <p className="text-xs text-ink-500">
              {tier} tier · <code className="font-mono">{tier}_MODEL</code>
            </p>
          </div>

          <div className="space-y-2">
            {TIER_CANDIDATES[tier].map((candidate) => {
              const isShippedDefault = candidate.model === TIER_DEFAULT_MODELS[tier];
              return (
                <div
                  key={candidate.model}
                  className={`rounded-[var(--radius-control)] border p-3 ${
                    isShippedDefault
                      ? "border-iris-400/40 bg-iris-400/[0.06]"
                      : "border-white/8 bg-white/[0.02]"
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-mono text-sm text-ink-100">{candidate.model}</p>
                    {isShippedDefault && <Badge tone="blue">shipped default</Badge>}
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-ink-400">{candidate.description}</p>
                </div>
              );
            })}
          </div>
        </Card>
      ))}
    </div>
  );
}
