import {
  type ExtensionAnalyzeResponse,
  type ExtensionCheckResponse,
  analyzeUrl,
  checkUrl,
  getVerdictColor,
  getVerdictLabel,
  subscribeEmail,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Mail,
  Play,
  Shield,
  ShieldBan,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

export const CLAUSEA_URL = "https://clausea.co";

type ViewState = "loading" | "loaded" | "error" | "not-found" | "crawl-failed";

// Sub-states within the "not-found" view
type NotFoundPhase =
  | "initial" // Show "Analyze" button (no pipeline active)
  | "pipeline-active" // Pipeline already running (detected on check)
  | "triggering" // User clicked "Analyze", waiting for response
  | "triggered" // Pipeline just started, show email input
  | "subscribing" // Submitting email
  | "subscribed" // Email subscribed successfully
  | "trigger-error" // Analyze call failed
  | "subscribe-error"; // Subscribe call failed

// ---------------------------------------------------------------------------
// Verdict palette — aligned with frontend Badge variants & semantic hex colors
// ---------------------------------------------------------------------------

const verdictPalette: Record<string, { badge: string; bar: string }> = {
  safe: {
    badge: "border-green-600/30 bg-green-500/15 text-green-600",
    bar: "bg-green-700",
  },
  caution: {
    badge: "border-amber-600/30 bg-amber-500/15 text-amber-600",
    bar: "bg-amber-600",
  },
  danger: {
    badge: "border-red-600/30 bg-red-500/15 text-red-600",
    bar: "bg-red-600",
  },
  gray: {
    badge: "border-border bg-muted text-muted-foreground",
    bar: "bg-muted-foreground",
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formatError = (error: unknown): string => {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "Something went wrong. Please try again.";
};

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [view, setView] = useState<ViewState>("loading");
  const [data, setData] = useState<ExtensionCheckResponse | null>(null);
  const [currentUrl, setCurrentUrl] = useState<string>("");
  const [error, setError] = useState<string>("");

  // Not-found / pipeline state
  const [notFoundPhase, setNotFoundPhase] = useState<NotFoundPhase>("initial");
  const [analyzeResult, setAnalyzeResult] =
    useState<ExtensionAnalyzeResponse | null>(null);
  const [email, setEmail] = useState<string>("");
  const [phaseError, setPhaseError] = useState<string>("");

  // The product slug for the subscribe call — comes from either check or analyze
  const productSlug = analyzeResult?.product_slug ?? data?.slug ?? null;

  // ── Fetch privacy analysis on mount ──────────────────────────────────────
  useEffect(() => {
    let mounted = true;

    const getActiveTabUrl = (): Promise<string> =>
      new Promise((resolve, reject) => {
        try {
          chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (chrome.runtime.lastError) {
              reject(chrome.runtime.lastError.message);
              return;
            }
            if (!tabs[0]?.url) {
              reject("Unable to detect the active tab URL.");
              return;
            }
            resolve(tabs[0].url);
          });
        } catch (err) {
          reject(err);
        }
      });

    const callBackground = (
      url: string,
    ): Promise<ExtensionCheckResponse | null> => {
      if (typeof chrome === "undefined" || !chrome.runtime?.id)
        return Promise.resolve(null);

      return new Promise((resolve, reject) => {
        try {
          chrome.runtime.sendMessage({ type: "CHECK_URL", url }, (response) => {
            if (chrome.runtime.lastError) {
              reject(chrome.runtime.lastError.message);
              return;
            }
            if (!response?.success) {
              reject(response?.error || "Background check failed");
              return;
            }
            resolve(response.data as ExtensionCheckResponse);
          });
        } catch (err) {
          reject(err);
        }
      });
    };

    const analyze = async () => {
      try {
        setView("loading");
        const url = await getActiveTabUrl();
        if (!mounted) return;
        setCurrentUrl(url);

        if (!url.startsWith("http")) {
          setView("not-found");
          return;
        }

        let analysis: ExtensionCheckResponse | null = null;
        try {
          analysis = await callBackground(url);
        } catch {
          analysis = await checkUrl(url);
        }

        if (!mounted) return;
        setData(analysis);

        if (analysis?.found) {
          setView("loaded");
        } else if (
          analysis?.pipeline_failed &&
          analysis.crawl_errors?.length
        ) {
          setView("crawl-failed");
        } else {
          setView("not-found");
          // Determine initial not-found phase based on pipeline status
          setNotFoundPhase(
            analysis?.pipeline_active ? "pipeline-active" : "initial",
          );
        }
      } catch (err) {
        if (!mounted) return;
        setError(formatError(err));
        setView("error");
      }
    };

    analyze();
    return () => {
      mounted = false;
    };
  }, []);

  // ── Trigger pipeline analysis ────────────────────────────────────────────
  const handleAnalyze = async () => {
    if (!currentUrl) return;
    setNotFoundPhase("triggering");
    setPhaseError("");
    try {
      const result = await analyzeUrl(currentUrl);
      setAnalyzeResult(result);

      if (result.status === "already_indexed") {
        // Product was indexed between our check and analyze — re-fetch
        const fresh = await checkUrl(currentUrl);
        setData(fresh);
        if (fresh.found) {
          setView("loaded");
          return;
        }
      }

      // "started" or "already_running" → show email input
      setNotFoundPhase("triggered");
    } catch (err) {
      setPhaseError(formatError(err));
      setNotFoundPhase("trigger-error");
    }
  };

  // ── Subscribe email for notification ─────────────────────────────────────
  const handleSubscribe = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!productSlug || !email.trim()) return;
    setNotFoundPhase("subscribing");
    setPhaseError("");
    try {
      await subscribeEmail(productSlug, email.trim());
      setNotFoundPhase("subscribed");
    } catch (err) {
      setPhaseError(formatError(err));
      setNotFoundPhase("subscribe-error");
    }
  };

  // ── Derived state ────────────────────────────────────────────────────────
  const tone = useMemo(() => {
    const key = getVerdictColor(data?.verdict ?? null);
    return verdictPalette[key] ?? verdictPalette.gray;
  }, [data]);

  const verdictLabel = data?.verdict
    ? getVerdictLabel(data.verdict)
    : "Unknown";

  // Is the pipeline running (either detected on check, or just triggered)?
  const pipelineRunning =
    notFoundPhase === "pipeline-active" ||
    notFoundPhase === "triggered" ||
    notFoundPhase === "subscribing" ||
    notFoundPhase === "subscribed" ||
    notFoundPhase === "subscribe-error";

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="flex min-h-[300px] w-[400px] flex-col bg-background text-foreground">
      {/* ── Header ── */}
      <header className="border-b border-border bg-card px-5 py-4">
        <div className="flex items-center gap-3">
          <img src="/logo.png" alt="Clausea" className="h-8 w-8" />
          <div>
            <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
              Privacy Pulse
            </p>
            <h1 className="text-sm font-semibold text-foreground">
              Trust what you sign in seconds
            </h1>
          </div>
        </div>
      </header>

      {/* ── Content ── */}
      <div className="stagger-children flex-1">
        {/* Loading */}
        {view === "loading" && (
          <section className="border-b border-border bg-card px-5 py-6">
            <div className="flex flex-col items-center gap-5 text-center">
              <div className="border border-border p-4 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" strokeWidth={1.5} />
              </div>
              <div>
                <p className="text-sm font-semibold">
                  Analyzing privacy policies...
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  This usually takes less than 2 seconds.
                </p>
              </div>
              <div className="w-full space-y-3">
                <div className="h-2.5 w-3/4 animate-pulse bg-muted" />
                <div className="h-2.5 w-full animate-pulse bg-muted" />
                <div className="h-2.5 w-2/3 animate-pulse bg-muted" />
              </div>
            </div>
          </section>
        )}

        {/* Error */}
        {view === "error" && (
          <section className="border-b border-border bg-card px-5 py-6">
            <div className="flex flex-col items-center gap-3 text-center">
              <div className="border border-border p-3 text-muted-foreground">
                <XCircle className="h-5 w-5" strokeWidth={1.5} />
              </div>
              <p className="text-sm font-semibold">
                Unable to complete analysis
              </p>
              <p className="text-xs text-muted-foreground">
                {error || "Please refresh the page or try again."}
              </p>
            </div>
          </section>
        )}

        {/* ── Not Found ── */}
        {view === "not-found" && (
          <section className="border-b border-border bg-card px-5 py-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="border border-border p-4 text-muted-foreground">
                <Shield className="h-6 w-6" strokeWidth={1.5} />
              </div>

              <div>
                <p className="text-sm font-semibold">
                  {pipelineRunning
                    ? "Analysis is underway"
                    : "Not analyzed yet"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {pipelineRunning
                    ? "We're crawling and analyzing this site's policies. This may take a few minutes."
                    : "We haven't analyzed this site yet. Start an analysis and we'll crawl their privacy policies."}
                </p>
              </div>

              {/* ── Phase: initial — show Analyze button ── */}
              {notFoundPhase === "initial" && (
                <button
                  type="button"
                  onClick={handleAnalyze}
                  className="flex w-full items-center justify-center gap-2 border border-foreground px-4 py-3 text-xs font-medium uppercase tracking-widest text-foreground transition-colors hover:bg-foreground hover:text-background"
                >
                  <Play className="h-3.5 w-3.5" strokeWidth={1.5} />
                  Analyze this site
                </button>
              )}

              {/* ── Phase: triggering — spinner on button ── */}
              {notFoundPhase === "triggering" && (
                <button
                  type="button"
                  disabled
                  className="flex w-full items-center justify-center gap-2 border border-border px-4 py-3 text-xs font-medium uppercase tracking-widest text-muted-foreground"
                >
                  <Loader2
                    className="h-3.5 w-3.5 animate-spin"
                    strokeWidth={1.5}
                  />
                  Starting analysis...
                </button>
              )}

              {/* ── Phase: trigger-error ── */}
              {notFoundPhase === "trigger-error" && (
                <div className="flex w-full flex-col items-center gap-3">
                  <div className="flex w-full flex-col items-center gap-2 border border-red-600/30 bg-red-500/10 p-4 text-red-600">
                    <AlertTriangle className="h-4 w-4" strokeWidth={1.5} />
                    <p className="text-xs">
                      {phaseError || "Failed to start analysis."}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleAnalyze}
                    className="text-xs font-medium text-foreground underline hover:no-underline"
                  >
                    Try again
                  </button>
                </div>
              )}

              {/* ── Phase: pipeline running — email subscription form ── */}
              {(notFoundPhase === "pipeline-active" ||
                notFoundPhase === "triggered" ||
                notFoundPhase === "subscribe-error") && (
                <div className="w-full space-y-3">
                  <div className="border-t border-border pt-4">
                    <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
                      Get notified when ready
                    </p>
                  </div>
                  <form
                    onSubmit={handleSubscribe}
                    className="flex w-full gap-2"
                  >
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@email.com"
                      className="flex-1 border border-border bg-background px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                    <button
                      type="submit"
                      className="flex items-center gap-1.5 border border-foreground px-3 py-2.5 text-xs font-medium text-foreground transition-colors hover:bg-foreground hover:text-background"
                    >
                      <Mail className="h-3 w-3" strokeWidth={1.5} />
                      Notify
                    </button>
                  </form>
                  {notFoundPhase === "subscribe-error" && (
                    <p className="text-xs text-red-600">
                      {phaseError || "Failed to subscribe. Please try again."}
                    </p>
                  )}
                </div>
              )}

              {/* ── Phase: subscribing ── */}
              {notFoundPhase === "subscribing" && (
                <div className="flex w-full items-center justify-center gap-2 border border-border p-4 text-muted-foreground">
                  <Loader2
                    className="h-3.5 w-3.5 animate-spin"
                    strokeWidth={1.5}
                  />
                  <p className="text-xs">Subscribing...</p>
                </div>
              )}

              {/* ── Phase: subscribed — success ── */}
              {notFoundPhase === "subscribed" && (
                <div className="flex w-full flex-col items-center gap-2 border border-green-600/30 bg-green-500/10 p-4 text-green-600">
                  <CheckCircle2 className="h-5 w-5" strokeWidth={1.5} />
                  <p className="text-xs font-medium">You&apos;re subscribed</p>
                  <p className="text-[10px] text-green-600/70">
                    We&apos;ll email{" "}
                    <span className="font-medium">{email}</span> when the
                    analysis is ready.
                  </p>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ── Crawl Failed ── */}
        {view === "crawl-failed" && data && (
          <section className="border-b border-border bg-card px-5 py-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="border border-amber-600/30 bg-amber-500/10 p-4 text-amber-600">
                <ShieldBan className="h-6 w-6" strokeWidth={1.5} />
              </div>

              <div>
                <p className="text-sm font-semibold">Unable to analyze</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {data.crawl_errors?.every(
                    (e) => e.error_type === "robots_txt_blocked",
                  )
                    ? "This site blocks automated access via robots.txt. We cannot crawl their legal documents."
                    : data.pipeline_error ??
                      "We were unable to crawl legal documents from this site."}
                </p>
              </div>

              {data.crawl_errors && data.crawl_errors.length > 0 && (
                <div className="w-full space-y-2 text-left">
                  <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
                    Failed URLs
                  </p>
                  {data.crawl_errors.slice(0, 3).map((err) => (
                    <div
                      key={err.url}
                      className="flex items-start gap-2 text-xs text-muted-foreground"
                    >
                      <ShieldBan
                        className="mt-0.5 h-3 w-3 shrink-0 text-amber-500"
                        strokeWidth={1.5}
                      />
                      <span className="break-all font-mono text-[10px]">
                        {err.url}
                      </span>
                    </div>
                  ))}
                  {data.crawl_errors.length > 3 && (
                    <p className="text-[10px] text-muted-foreground">
                      ...and {data.crawl_errors.length - 3} more
                    </p>
                  )}
                </div>
              )}

              {data.analysis_url && (
                <button
                  type="button"
                  onClick={() => window.open(data!.analysis_url!, "_blank")}
                  className="flex w-full items-center justify-center gap-2 border border-border px-4 py-3 text-xs font-medium uppercase tracking-widest text-muted-foreground transition-colors hover:bg-muted"
                >
                  View details
                  <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
                </button>
              )}
            </div>
          </section>
        )}

        {/* ── Loaded ── */}
        {view === "loaded" && data && (
          <>
            {/* Verdict */}
            <section className="border-b border-border bg-card">
              <div className="border-b border-border px-5 py-3">
                <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
                  Privacy verdict
                </p>
              </div>
              <div className="px-5 py-4">
                <div className="flex flex-col gap-4">
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="text-lg font-semibold">
                      {data.product_name}
                    </h2>
                    <span
                      className={cn(
                        "shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
                        tone.badge,
                      )}
                    >
                      {verdictLabel}
                    </span>
                  </div>

                  {data.risk_score !== null && (
                    <div>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>Risk score</span>
                        <span className="font-semibold text-foreground">
                          {data.risk_score}/10
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 bg-muted">
                        <div
                          className={cn(
                            "h-full transition-all duration-500",
                            tone.bar,
                          )}
                          style={{ width: `${data.risk_score * 10}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {data.one_line_summary && (
                    <p className="border-l-2 border-border py-2 pl-3 text-xs leading-relaxed text-muted-foreground">
                      {data.one_line_summary}
                    </p>
                  )}
                </div>
              </div>
            </section>

            {/* Top concerns */}
            {data.top_concerns && data.top_concerns.length > 0 && (
              <section className="border-b border-border bg-card">
                <div className="border-b border-border px-5 py-3">
                  <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
                    Top concerns
                  </p>
                </div>
                <div className="px-5 py-4">
                  <ol className="space-y-3">
                    {data.top_concerns.slice(0, 3).map((concern) => (
                      <li
                        key={concern}
                        className="flex gap-2.5 text-xs leading-relaxed text-muted-foreground"
                      >
                        <TriangleAlert
                          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500"
                          strokeWidth={1.5}
                        />
                        <span>{concern}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              </section>
            )}

            {/* CTA — inverted (matches frontend dark-on-light pattern) */}
            <section className="bg-foreground px-5 py-5 text-background">
              <div className="space-y-3">
                <p className="text-[10px] uppercase tracking-[0.3em] text-background/50">
                  Deep dive
                </p>
                <p className="text-base font-semibold">
                  See the clause-by-clause analysis
                </p>
                <p className="text-xs leading-relaxed text-background/60">
                  Read every policy excerpt, risk rationale, and recommended
                  actions.
                </p>
                {data.analysis_url && (
                  <button
                    type="button"
                    onClick={() => window.open(data.analysis_url!, "_blank")}
                    className="flex w-full items-center justify-center gap-2 border border-background/30 px-4 py-3 text-xs font-medium uppercase tracking-widest text-background transition-colors hover:bg-background hover:text-foreground"
                  >
                    View full report
                    <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
                  </button>
                )}
              </div>
            </section>
          </>
        )}
      </div>

      {/* ── Footer ── */}
      <footer className="border-t border-border px-5 py-3 text-center">
        <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">
          Powered by{" "}
          <span className="font-semibold text-foreground">Clausea</span>
        </p>
      </footer>
    </div>
  );
}
