"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { askAssistant } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import MermaidDiagram from "@/components/admin/MermaidDiagram";
import { 
  X, Maximize2, Minimize2, Trash2, Copy, Check, ThumbsUp, ThumbsDown, 
  Sparkles, Send, Terminal, MessageSquareText
} from "lucide-react";

const CLIENT_PROMPTS = [
  "How do I check holiday conflicts?",
  "Explain the greenlight process",
  "What is the tier system?",
];

const ADMIN_PROMPTS = [
  "How many agents are available?",
  "How does the Release Planner work?",
  "What is shown on the Evals tab?",
];

const CLIENT_PLACEHOLDERS = [
  "Try: 'Check conflicts for a July release...'",
  "Try: 'What genres are missing this year?'",
  "Ask about studio operations...",
];

const ADMIN_PLACEHOLDERS = [
  "Try: 'Explain the 4 available agents'",
  "Try: 'How do I use the memory tab?'",
  "Ask about studio tools and UI...",
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  return (
    <button 
      onClick={handleCopy}
      className="text-ink-400 hover:text-ink-100 transition-colors"
      title="Copy response"
    >
      {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
    </button>
  );
}

function FeedbackButtons() {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  
  return (
    <div className="flex items-center gap-2">
      <button 
        onClick={() => setFeedback("up")}
        className={`transition-colors ${feedback === "up" ? "text-emerald-400" : "text-ink-400 hover:text-ink-100"}`}
        title="Helpful"
      >
        <ThumbsUp size={14} />
      </button>
      <button 
        onClick={() => setFeedback("down")}
        className={`transition-colors ${feedback === "down" ? "text-red-400" : "text-ink-400 hover:text-ink-100"}`}
        title="Not helpful"
      >
        <ThumbsDown size={14} />
      </button>
    </div>
  );
}

export function HelpChat({ 
  variant, 
  onNavigate,
  validTabs
}: { 
  variant: "client" | "developer",
  onNavigate?: (tabId: string) => void,
  validTabs?: string[]
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [query, setQuery] = useState("");
  const [history, setHistory] = useState<{ role: "user" | "bot"; text: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  
  const prompts = variant === "client" ? CLIENT_PROMPTS : ADMIN_PROMPTS;
  const placeholders = variant === "client" ? CLIENT_PLACEHOLDERS : ADMIN_PLACEHOLDERS;

  // Cycle placeholders
  useEffect(() => {
    if (!isOpen) return;
    const interval = setInterval(() => {
      setPlaceholderIndex((prev) => (prev + 1) % placeholders.length);
    }, 4000);
    return () => clearInterval(interval);
  }, [isOpen, placeholders.length]);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
      if (e.key === 'Escape' && isOpen) {
        e.preventDefault();
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  // Focus input on open
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history, loading]);

  const handleSubmit = async (userText: string) => {
    if (!userText.trim() || loading) return;

    setQuery("");
    setHistory((prev) => [...prev, { role: "user", text: userText }]);
    setLoading(true);

    try {
      const response = await askAssistant(variant, userText);
      setHistory((prev) => [...prev, { role: "bot", text: response }]);
    } catch (err) {
      setHistory((prev) => [...prev, { role: "bot", text: "Sorry, something went wrong processing your request." }]);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setHistory([]);
  };

  // Memoize components to prevent MermaidDiagram from unmounting on every HelpChat render (which runs every 4s due to placeholder interval)
  const markdownComponents = useMemo(() => ({
    a: ({node, href, children, ...props}: any) => {
      const tabId = href?.replace('#tab-', '');
      if (href?.startsWith('#tab-') && onNavigate && (!validTabs || validTabs.includes(tabId))) {
        return (
          <button 
            onClick={() => {
              onNavigate(tabId);
              setIsOpen(false);
            }}
            className="inline-flex items-center rounded bg-iris-400/10 px-1 py-0.5 text-xs font-medium text-iris-400 mx-1 border border-iris-400/20 hover:bg-iris-400/20 no-underline"
          >
            {children}
          </button>
        );
      }
      return (
        <a 
          href={href} 
          className="inline-flex items-center rounded bg-iris-400/10 px-1 py-0.5 text-xs font-medium text-iris-400 mx-1 border border-iris-400/20 hover:bg-iris-400/20 no-underline"
          {...props}
        >
          {children}
        </a>
      );
    },
    code({ node, inline, className, children, ...props }: any) {
      const match = /language-(\w+)/.exec(className || "");
      if (!inline && match?.[1] === "mermaid") {
        return (
          <div className="my-4 rounded-xl border border-white/10 bg-white/5 p-4 overflow-x-auto">
            <MermaidDiagram source={String(children).replace(/\n$/, "")} />
          </div>
        );
      }
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    }
  }), [onNavigate]);

  // Custom markdown component to parse citations
  const renderMarkdown = (text: string) => {
    return (
      <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed prose-pre:bg-ink-950 prose-pre:border prose-pre:border-white/10">
        <ReactMarkdown components={markdownComponents}>
          {text}
        </ReactMarkdown>
      </div>
    );
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="press flex items-center gap-2 rounded-full border border-white/8 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-ink-400 hover:border-white/15 hover:text-ink-100 group transition-all"
      >
        <Sparkles size={14} className="text-iris-400 group-hover:text-iris-300" />
        <span className="hidden sm:inline">Ask AI</span>
        <span className="opacity-50 text-[10px] hidden md:inline ml-1 border border-white/10 rounded px-1 group-hover:border-white/20">⌘K</span>
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[8vh] sm:pt-[10vh] bg-black/60 backdrop-blur-sm px-4">
          <div 
            className={`w-full ${isExpanded ? 'max-w-5xl h-[85vh]' : 'max-w-2xl h-[70vh] max-h-[800px]'} 
              rounded-2xl border border-white/10 bg-ink-950 shadow-2xl flex flex-col overflow-hidden transition-all duration-300 ease-[var(--ease-out-quint)]`}
          >
            
            {/* Header */}
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3 bg-ink-900/50 shrink-0">
              <div className="flex items-center gap-2">
                {variant === "developer" ? (
                  <Terminal size={16} className="text-iris-400" />
                ) : (
                  <MessageSquareText size={16} className="text-iris-400" />
                )}
                <span className="text-sm font-medium text-ink-100">
                  {variant === "developer" ? "Admin Assistant" : "Studio Assistant"}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {history.length > 0 && (
                  <button onClick={clearChat} className="text-ink-400 hover:text-ink-100 transition-colors" title="Clear chat">
                    <Trash2 size={16} />
                  </button>
                )}
                <button onClick={() => setIsExpanded(!isExpanded)} className="text-ink-400 hover:text-ink-100 transition-colors" title={isExpanded ? "Collapse" : "Expand"}>
                  {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                </button>
                <button onClick={() => setIsOpen(false)} className="text-ink-400 hover:text-ink-100 transition-colors" title="Close (Esc)">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Chat Area */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 scroll-smooth">
              
              {history.length === 0 && (
                <div className="flex flex-col items-center justify-center text-center mt-8 space-y-8 animate-fade-in">
                  
                  {/* Welcome Banner */}
                  <div className="space-y-2">
                    <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-iris-500/10 border border-iris-500/20 mb-2">
                      <Sparkles className="text-iris-400" size={24} />
                    </div>
                    <h2 className="text-xl font-semibold text-ink-50">
                      Hi, how can I help?
                    </h2>
                    <p className="text-sm text-ink-400 max-w-[80%] mx-auto leading-relaxed">
                      {variant === 'developer' 
                        ? "I have deep knowledge of the Agentic Studio UI, the 4 specialized agents, and our admin workflows." 
                        : "I can help with release planning, studio operations, and understanding our metrics."}
                    </p>
                  </div>

                  {/* Quick Prompts */}
                  <div className="w-full max-w-lg space-y-3">
                    <p className="text-xs font-medium text-ink-500 uppercase tracking-wider">Suggested Actions</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {prompts.map((p, i) => (
                        <button
                          key={i}
                          onClick={() => handleSubmit(p)}
                          className="text-left px-4 py-2.5 rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/15 transition-all text-sm text-ink-300 hover:text-ink-100"
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Message List */}
              {history.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} animate-slide-up`}>
                  <div className={`max-w-[85%] rounded-2xl px-5 py-3.5 text-sm ${
                    msg.role === "user" 
                      ? "bg-iris-500 text-white shadow-md shadow-iris-500/10" 
                      : "bg-white/5 text-ink-100 border border-white/5"
                  }`}>
                    {msg.role === "user" ? (
                      msg.text
                    ) : (
                      <div className="space-y-2">
                        {renderMarkdown(msg.text)}
                        
                        {/* Action Bar for Bot */}
                        <div className="flex items-center justify-end gap-3 pt-2 mt-2 border-t border-white/5">
                          <FeedbackButtons />
                          <div className="w-px h-3 bg-white/10" />
                          <CopyButton text={msg.text} />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              
              {/* Loading State */}
              {loading && (
                <div className="flex justify-start animate-fade-in">
                  <div className="max-w-[85%] rounded-2xl bg-white/5 border border-white/5 px-5 py-4">
                    <div className="flex space-x-1.5 items-center justify-center h-4">
                      <div className="w-1.5 h-1.5 bg-ink-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                      <div className="w-1.5 h-1.5 bg-ink-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                      <div className="w-1.5 h-1.5 bg-ink-400 rounded-full animate-bounce"></div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Input Form */}
            <div className="p-4 bg-ink-900/80 border-t border-white/10 shrink-0">
              <form 
                onSubmit={(e) => { e.preventDefault(); handleSubmit(query); }} 
                className="relative flex items-center"
              >
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={placeholders[placeholderIndex]}
                  className="w-full rounded-xl bg-ink-950 border border-white/10 px-4 py-3.5 pr-12 text-sm text-ink-50 placeholder:text-ink-500 focus:outline-none focus:border-iris-400/50 focus:ring-1 focus:ring-iris-400/50 transition-all shadow-inner"
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={!query.trim() || loading}
                  className={`absolute right-2 p-2 rounded-lg transition-colors ${
                    query.trim() && !loading
                      ? 'bg-iris-500 text-white hover:bg-iris-400' 
                      : 'text-ink-600 cursor-not-allowed'
                  }`}
                >
                  <Send size={16} className={query.trim() && !loading ? 'translate-x-[1px] translate-y-[-1px]' : ''} />
                </button>
              </form>
              <div className="text-center mt-2">
                <span className="text-[10px] text-ink-600 font-medium">
                  AI can make mistakes. Verify important information.
                </span>
              </div>
            </div>

          </div>
          
          {/* Click outside overlay */}
          <div className="absolute inset-0 -z-10" onClick={() => setIsOpen(false)} />
        </div>
      )}
    </>
  );
}
