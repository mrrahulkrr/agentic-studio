"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DocEntry, getDoc, listDocs } from "@/lib/api";
import { Card, EmptyState, ErrorAlert, Spinner, errorMessage } from "@/components/ui";
import MermaidDiagram from "@/components/admin/MermaidDiagram";
import { DOCS_COPY } from "@/lib/content";

/** Backend is the source of truth for which docs exist; this is only the
 * picker's display order, which mirrors DOC_REGISTRY's own key order. */
const DOC_ORDER = DOCS_COPY.docs.map((d) => d.key);

export default function DocsPanel() {
  const [docs, setDocs] = useState<DocEntry[] | null>(null);
  const [key, setKey] = useState<string>(DOC_ORDER[0]);

  const [loaded, setLoaded] = useState<{ key: string; text: string } | null>(null);
  /** Tied to the key that failed, so picking a different doc clears it by itself. */
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);

  const error = failure?.key === key ? failure.message : "";
  const loading = loaded?.key !== key && !error;

  // Fetch the list of docs (for title sync with backend registry).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await listDocs();
        if (!cancelled) setDocs(res.docs);
      } catch {
        // The picker still works off DOCS_COPY.docs if this fails.
        if (!cancelled) setDocs([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Fetch content for the selected doc.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const text = await getDoc(key);
        if (!cancelled) setLoaded({ key, text });
      } catch (err) {
        if (!cancelled) setFailure({ key, message: errorMessage(err) });
      }
    })();
    return () => { cancelled = true; };
  }, [key]);

  function titleFor(docKey: string): string {
    return docs?.find((d) => d.key === docKey)?.title
      ?? DOCS_COPY.docs.find((d) => d.key === docKey)?.title
      ?? docKey;
  }

  return (
    <div className="space-y-6">
      <Card className="space-y-2">
        <h2 className="font-semibold">{DOCS_COPY.title}</h2>
        <p className="text-sm leading-relaxed text-ink-300">{DOCS_COPY.intro}</p>
      </Card>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {DOC_ORDER.map((docKey) => {
          const active = docKey === key;
          return (
            <button
              key={docKey}
              onClick={() => setKey(docKey)}
              className={`press rounded-[var(--radius-surface)] border p-3 text-left transition-colors ${
                active ? "border-iris-400 bg-iris-500/10" : "border-white/8 bg-white/[0.03] hover:border-white/15"
              }`}
            >
              <p className={`text-sm font-medium ${active ? "text-iris-200" : "text-ink-100"}`}>
                {titleFor(docKey)}
              </p>
            </button>
          );
        })}
      </div>

      {error && <ErrorAlert message={error} />}

      {loading && !error && (
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-400">
          <Spinner /> {DOCS_COPY.loading}
        </div>
      )}

      {!loading && !error && loaded && loaded.key === key && loaded.text.trim() === "" && (
        <Card>
          <EmptyState title={DOCS_COPY.empty} hint={DOCS_COPY.intro} />
        </Card>
      )}

      {!loading && !error && loaded && loaded.key === key && loaded.text.trim() !== "" && (
        <Card className="animate-fade-in-up !p-8">
          <article className="max-w-none space-y-4 text-sm leading-relaxed text-ink-300">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => (
                  <h1 className="mt-6 text-xl font-semibold text-ink-50 first:mt-0">{children}</h1>
                ),
                h2: ({ children }) => (
                  <h2 className="mt-6 border-b border-white/8 pb-2 text-lg font-semibold text-ink-50 first:mt-0">
                    {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3 className="mt-5 text-base font-semibold text-ink-100">{children}</h3>
                ),
                h4: ({ children }) => <h4 className="mt-4 font-semibold text-ink-100">{children}</h4>,
                p: ({ children }) => <p className="leading-relaxed">{children}</p>,
                a: ({ href, children }) => (
                  <a href={href} target="_blank" rel="noreferrer" className="text-iris-300 underline underline-offset-2 hover:text-iris-200">
                    {children}
                  </a>
                ),
                ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
                li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                blockquote: ({ children }) => (
                  <blockquote className="border-l-2 border-iris-400/40 pl-3 text-ink-400">{children}</blockquote>
                ),
                hr: () => <hr className="border-white/8" />,
                table: ({ children }) => (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-left text-xs">{children}</table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="border border-white/8 bg-white/[0.03] px-2.5 py-1.5 font-medium text-ink-200">
                    {children}
                  </th>
                ),
                td: ({ children }) => <td className="border border-white/8 px-2.5 py-1.5">{children}</td>,
                pre: ({ children }) => (
                  <pre className="overflow-x-auto rounded-[var(--radius-control)] border border-white/8 bg-ink-950/60 p-3 text-xs">
                    {children}
                  </pre>
                ),
                code(props) {
                  const { className, children, ...rest } = props;
                  const match = /language-(\w+)/.exec(className ?? "");
                  // Mermaid gets its own renderer; all other languages fall through
                  // to a plain <code> element.
                  if (match?.[1] === "mermaid") {
                    return <MermaidDiagram source={String(children).replace(/\n$/, "")} />;
                  }
                  return (
                    <code
                      className={`font-mono text-ink-200 ${className ?? "rounded bg-ink-950/60 px-1 py-0.5 text-xs"}`}
                      {...rest}
                    >
                      {children}
                    </code>
                  );
                },
              }}
            >
              {loaded.text}
            </ReactMarkdown>
          </article>
        </Card>
      )}
    </div>
  );
}
