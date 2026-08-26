"use client";

import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { Spinner } from "@/components/ui";

// svg-pan-zoom's type definition is bundled with the package.
type PanZoomInstance = { zoomIn(): void; zoomOut(): void; reset(): void; destroy(): void };

let initialized = false;

function ensureInitialized() {
  if (initialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    themeVariables: {
      // Keep background transparent so the card's own bg shows through.
      background: "transparent",
      mainBkg: "#1e1e2e",
      nodeBorder: "#6366f1",
      clusterBkg: "#13131f",
      titleColor: "#e2e8f0",
      edgeLabelBackground: "#1e1e2e",
      lineColor: "#6366f1",
      fontFamily: "var(--font-sans, 'Inter'), sans-serif",
    },
  });
  initialized = true;
}

/** One id per mounted diagram — mermaid.render() needs a DOM id of its own. */
let counter = 0;

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

  useEffect(() => {
    if (!svg || !containerRef.current) return;
    const svgEl = containerRef.current.querySelector("svg");
    if (!svgEl) return;

    svgEl.removeAttribute("style");
    svgEl.setAttribute("width", "100%");
    svgEl.setAttribute("height", "100%");

    let destroyed = false;
    let instance: PanZoomInstance | null = null;
    // Dynamic import: svg-pan-zoom touches `window` at call time and this
    // component is otherwise SSR-safe, so the import is deferred to a
    // client-only effect rather than running during Next's server render pass.
    import("svg-pan-zoom").then(({ default: svgPanZoom }) => {
      if (destroyed) return;
      instance = svgPanZoom(svgEl, {
        zoomEnabled: true,
        panEnabled: true,
        controlIconsEnabled: false,
        fit: false,
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

  function zoomIn() { panZoomRef.current?.zoomIn(); }
  function zoomOut() { panZoomRef.current?.zoomOut(); }
  function resetView() { panZoomRef.current?.reset(); }

  function downloadSvg() {
    if (!svg) return;
    const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
    downloadBlob(blob, `${idRef.current}.svg`);
  }

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
      {/* Fixed height + overflow-hidden: svg-pan-zoom owns panning via an
          internal transform, so a browser scrollbar would fight it. */}
      <div
        ref={containerRef}
        className="h-[70vh] overflow-hidden p-4"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  );
}
