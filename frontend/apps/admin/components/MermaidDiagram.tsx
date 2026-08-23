// Renders one ```mermaid fenced block from a doc. react-markdown does not render
// Mermaid itself — see DocsPanel.tsx's `code` override, which hands a block off
// to this component instead of the default <code> element whenever its language
// is "mermaid". Every other fenced language falls through to that default.
"use client";

import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { Spinner } from "@/components/ui";

// @types/svg-pan-zoom declares a global `SvgPanZoom` namespace rather than
// exporting types from the module itself, so the instance type is referenced
// that way rather than as a named import.
type PanZoomInstance = SvgPanZoom.Instance;

let initialized = false;

/** Runs once no matter how many diagrams are on screen. `theme: "dark"` alone
 * is not enough: Mermaid's built-in dark theme never sets `nodeTextColor` for
 * itself (see theme-dark.js's `updateColors()` — every other bundled theme
 * assigns it from `primaryTextColor`, dark's doesn't), so flowchart labels
 * silently fall back to a hardcoded `textColor: "#ccc"` that has nothing to
 * do with this app's palette and isn't guaranteed to contrast against every
 * fill Mermaid derives (classDef'd nodes, alt subgraph fills, etc. can end up
 * lighter than the ~#1f2020 default `mainBkg` that `#ccc` was tuned for) —
 * that mismatch is what showed up as gray boxes with barely-legible text.
 * themeVariables pins every color Mermaid actually uses to this app's own
 * ink-* tokens (globals.css) instead, so labels always resolve against a
 * background this app really paints. Confirmed against globals.css's actual
 * hex values and re-verified with a real rendered screenshot after the
 * pan/zoom rework below — see MermaidDiagram verification notes.
 *
 * securityLevel is "loose", not the default "strict": under "strict" mermaid
 * runs its SVG output through DOMPurify, which strips the <style> block the
 * diagram's own theme (colors, fonts, edges) lives in — every diagram renders
 * as unstyled bare shapes with invisible text. Safe here because the source is
 * always a developer-gated repo doc (see DocsPanel.tsx), never arbitrary user
 * input. */
function ensureInitialized() {
  if (initialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    securityLevel: "loose",
    themeVariables: {
      background: "#050811", // --color-ink-950
      textColor: "#e4e4e7", // --color-ink-100
      nodeTextColor: "#e4e4e7", // --color-ink-100 — the value dark's own theme never sets
      primaryColor: "#12161f", // --color-ink-800 — node fill
      primaryTextColor: "#e4e4e7", // --color-ink-100
      primaryBorderColor: "#2a2d34", // --color-ink-600
      secondaryColor: "#1c212c", // --color-ink-700
      secondaryTextColor: "#e4e4e7",
      secondaryBorderColor: "#2a2d34",
      tertiaryColor: "#0e131d", // --color-ink-850
      tertiaryTextColor: "#e4e4e7",
      tertiaryBorderColor: "#2a2d34",
      lineColor: "#454952", // --color-ink-500
      mainBkg: "#12161f", // --color-ink-800
      nodeBorder: "#2a2d34", // --color-ink-600
      clusterBkg: "#0e131d", // --color-ink-850
      clusterBorder: "#2a2d34", // --color-ink-600
      titleColor: "#ffffff", // --color-ink-50
      edgeLabelBackground: "#050811", // --color-ink-950
      fontFamily: "var(--font-sans, 'Source Sans 3'), sans-serif",
    },
  });
  initialized = true;
}

/** One id per mounted diagram — mermaid.render() needs a DOM id of its own. */
let counter = 0;

/** Triggers a browser download of a Blob without any library — an <a download>
 * appended, clicked, and removed. Works for both the SVG and PNG buttons below. */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function MermaidDiagram({ source }: { source: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const idRef = useRef(`mermaid-${++counter}`);
  const containerRef = useRef<HTMLDivElement>(null);
  const panZoomRef = useRef<PanZoomInstance | null>(null);

  // Async IIFE with a cancelled guard, same as every other fetch-driven effect
  // in this codebase (see DatabasePanel.tsx) — a bare setState in the effect
  // body fails the build's react-hooks/set-state-in-effect rule.
  useEffect(() => {
    let cancelled = false;
    ensureInitialized();
    (async () => {
      try {
        const { svg: rendered } = await mermaid.render(idRef.current, source);
        if (!cancelled) {
          setSvg(rendered);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setSvg(null);
          setError(err instanceof Error ? err.message : "Could not render this diagram.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [source]);

  // Mermaid's own <svg> ships `width="100%"` and `style="max-width:<viewBox
  // width>px"`, meant for diagrams that comfortably fit their container. A
  // large architecture diagram's viewBox can be tens of thousands of user
  // units across, and shrinking that down to the container's width scales
  // 16px labels down to sub-pixel — illegible boxes with no visible text (and,
  // once the color fix above made node fills and background contrast, the
  // sub-pixel shapes stopped being visible at all — scattered marks on a
  // plain background, confirmed in a real rendered screenshot).
  //
  // The fix is two parts, not one: stripping the inline width/style *and*
  // handing the SVG to svg-pan-zoom so the diagram gets an explicit zoom
  // level a person controls, instead of one CSS max-width computed once at
  // render time. svg-pan-zoom needs the SVG to actually fill its container
  // (width/height: 100%) so it has a viewport to pan within — that's
  // opposite of the old "strip and let it overflow-scroll at intrinsic size"
  // approach, which is why the container below changed from
  // max-h + overflow-auto (scrollbars) to a fixed height + overflow hidden
  // (pan/zoom replaces the scrollbar).
  useEffect(() => {
    if (!svg || !containerRef.current) return;
    const svgEl = containerRef.current.querySelector("svg");
    if (!svgEl) return;

    svgEl.removeAttribute("style");
    svgEl.setAttribute("width", "100%");
    svgEl.setAttribute("height", "100%");

    let destroyed = false;
    let instance: PanZoomInstance | null = null;
    // Dynamic import, not a module-level one: svg-pan-zoom touches `window`
    // at call time and this component is otherwise SSR-safe, so the import
    // is deferred to inside a client-only effect rather than risking it
    // running during Next's server render pass.
    import("svg-pan-zoom").then(({ default: svgPanZoom }) => {
      if (destroyed) return;
      instance = svgPanZoom(svgEl, {
        zoomEnabled: true,
        panEnabled: true,
        controlIconsEnabled: false, // custom toolbar below instead
        fit: false, // render at native (1 user unit = 1px) scale, not shrunk to fit
        center: true,
        minZoom: 0.05,
        maxZoom: 10,
        zoomScaleSensitivity: 0.35,
      });
      panZoomRef.current = instance;
    });

    return () => {
      destroyed = true;
      instance?.destroy();
      panZoomRef.current = null;
    };
  }, [svg]);

  function zoomIn() {
    panZoomRef.current?.zoomIn();
  }
  function zoomOut() {
    panZoomRef.current?.zoomOut();
  }
  function resetView() {
    panZoomRef.current?.reset();
  }

  // Downloads always come from the pristine `svg` string mermaid.render()
  // produced, never from the live DOM node — svg-pan-zoom rewrites that node
  // (wraps it in its own <g>, overwrites width/height/viewBox as the user
  // pans and zooms), so reading it back out would export whatever partial
  // view the user happens to be looking at instead of the whole diagram.
  function downloadSvg() {
    if (!svg) return;
    const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
    downloadBlob(blob, `${idRef.current}.svg`);
  }

  // PNG export was tried (Image → <canvas> → toBlob) and dropped: Mermaid
  // renders every label through a `<foreignObject>` (confirmed on the real
  // rendered SVG — `svg.innerHTML.includes("foreignObject")` is true), and
  // browsers treat any canvas drawn from an SVG containing foreignObject as
  // tainted for security reasons, regardless of same-origin blob/data URLs.
  // `canvas.toBlob()` throws "Tainted canvases may not be exported" every
  // time — reproduced in a real headless-browser run, not a theoretical
  // concern. A real fix needs either a rasterization library that walks the
  // SVG itself (canvg, html-to-image — a new dependency) or a global switch
  // to `htmlLabels: false`, which would reflow text on every diagram in the
  // app. Neither is "download button, dependency-free" scope, so SVG export
  // below is the only download offered for now.

  if (error) {
    return (
      <div className="my-3 rounded-[var(--radius-control)] border border-red-500/25 bg-red-500/8 px-3 py-2 text-xs text-red-200">
        Couldn&apos;t render this diagram: {error}
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="my-3 flex items-center gap-2 rounded-[var(--radius-control)] border border-white/8 bg-white/[0.02] px-3 py-4 text-xs text-ink-400">
        <Spinner /> Rendering diagram…
      </div>
    );
  }

  const toolbarButtonClass =
    "press rounded-[var(--radius-control)] border border-white/8 bg-white/[0.03] px-2.5 py-1 text-xs text-ink-300 transition-colors hover:border-white/15 hover:text-ink-100";

  // The SVG string comes from mermaid.render() itself, not from the markdown
  // text directly — it is the library's own output for source read from a
  // developer-gated repo doc, not arbitrary user input.
  //
  // Fixed height + overflow-hidden (not max-h + overflow-auto): svg-pan-zoom
  // owns panning via an internal transform now, so a browser scrollbar on
  // this element would fight it. The diagram itself renders at native scale
  // inside that viewport; zoom/reset controls (and wheel-zoom, drag-to-pan,
  // both wired up by svg-pan-zoom) are how a large diagram gets navigated.
  return (
    <div className="my-3 rounded-[var(--radius-control)] border border-white/8 bg-white/[0.02]">
      <div className="flex items-center justify-between gap-2 border-b border-white/8 px-3 py-2">
        <div className="flex gap-1.5">
          <button type="button" onClick={zoomOut} className={toolbarButtonClass} aria-label="Zoom out">
            −
          </button>
          <button type="button" onClick={zoomIn} className={toolbarButtonClass} aria-label="Zoom in">
            +
          </button>
          <button type="button" onClick={resetView} className={toolbarButtonClass}>
            Reset view
          </button>
        </div>
        <div className="flex gap-1.5">
          <button type="button" onClick={downloadSvg} className={toolbarButtonClass}>
            Download SVG
          </button>
        </div>
      </div>
      <div
        ref={containerRef}
        className="h-[70vh] overflow-hidden p-4"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  );
}
