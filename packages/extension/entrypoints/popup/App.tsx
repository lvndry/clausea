import {
  type ExtensionCheckResponse,
  checkUrl,
  getVerdictColor,
  getVerdictLabel,
  requestSupport,
} from "@/lib/api";
import {
  AlertTriangle,
  BellPlus,
  CheckCircle2,
  Loader2,
  Shield,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

export const CLAUSEA_URL = "https://clausea.co";

type ViewState = "loading" | "loaded" | "error" | "not-found";

interface UiBlockProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
}

const Card = ({ title, children, className = "" }: UiBlockProps) => (
  <section
    className={`rounded-2xl border border-slate-200/80 bg-white shadow-[0_10px_40px_rgba(15,23,42,0.05)] ${className}`}
  >
    {title ? (
      <div className="border-b border-slate-100 px-5 py-3">
        <p className="text-sm font-medium text-slate-600">{title}</p>
      </div>
    ) : null}
    <div className="px-5 py-4">{children}</div>
  </section>
);

const FallbackCard = ({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) => (
  <Card>
    <div className="flex flex-col items-center gap-3 text-center">
      <div className="rounded-full bg-slate-100 p-3 text-slate-500">{icon}</div>
      <div>
        <p className="text-base font-semibold text-slate-800">{title}</p>
        <p className="text-sm text-slate-500">{description}</p>
      </div>
    </div>
  </Card>
);

const shimmerLine =
  "h-3 rounded-full bg-gradient-to-r from-slate-100 via-slate-200 to-slate-100 animate-[shimmer_1.8s_infinite]";

const LoadingState = () => (
  <Card>
    <div className="flex flex-col items-center gap-4 text-center">
      <div className="rounded-full border border-slate-200 p-4 text-indigo-500">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
      <div>
        <p className="text-base font-semibold text-slate-800">
          Analyzing privacy policies…
        </p>
        <p className="text-sm text-slate-500">
          This usually takes less than 2 seconds.
        </p>
      </div>
      <div className="w-full space-y-3">
        <div className={`${shimmerLine} w-3/4`} />
        <div className={`${shimmerLine} w-full`} />
        <div className={`${shimmerLine} w-2/3`} />
      </div>
    </div>
  </Card>
);

const verdictPalette: Record<
  string,
  { bg: string; text: string; border: string }
> = {
  safe: {
    bg: "bg-emerald-50",
    text: "text-emerald-600",
    border: "border-emerald-200",
  },
  caution: {
    bg: "bg-amber-50",
    text: "text-amber-600",
    border: "border-amber-200",
  },
  danger: {
    bg: "bg-rose-50",
    text: "text-rose-600",
    border: "border-rose-200",
  },
  gray: {
    bg: "bg-slate-50",
    text: "text-slate-600",
    border: "border-slate-200",
  },
};

const formatError = (error: unknown) => {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "Something went wrong. Please try again.";
};

export default function App() {
  const [view, setView] = useState<ViewState>("loading");
  const [data, setData] = useState<ExtensionCheckResponse | null>(null);
  const [currentUrl, setCurrentUrl] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [supportStatus, setSupportStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");
  const [supportError, setSupportError] = useState<string>("");

  useEffect(() => {
    let mounted = true;

    const getActiveTabUrl = async () =>
      new Promise<string>((resolve, reject) => {
        try {
          chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (chrome.runtime.lastError) {
              reject(chrome.runtime.lastError.message);
              return;
            }
            const tab = tabs[0];
            if (!tab?.url) {
              reject("Unable to detect the active tab URL.");
              return;
            }
            resolve(tab.url);
          });
        } catch (err) {
          reject(err);
        }
      });

    const callBackground = async (url: string) => {
      if (typeof chrome === "undefined" || !chrome.runtime?.id) return null;
      return new Promise<ExtensionCheckResponse | null>((resolve, reject) => {
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
        setView(analysis?.found ? "loaded" : "not-found");
        setSupportStatus("idle");
        setSupportError("");
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

  const handleSupportRequest = async () => {
    if (
      !currentUrl ||
      supportStatus === "loading" ||
      supportStatus === "success"
    )
      return;
    setSupportStatus("loading");
    setSupportError("");
    try {
      await requestSupport(currentUrl);
      setSupportStatus("success");
    } catch (err) {
      setSupportStatus("error");
      setSupportError(formatError(err));
    }
  };

  const verdictTone = useMemo(() => {
    const paletteKey = getVerdictColor(data?.verdict as any);
    return verdictPalette[paletteKey] ?? verdictPalette.gray;
  }, [data]);

  const verdictLabel = data?.verdict
    ? getVerdictLabel(data.verdict)
    : "Unknown";

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-50 text-slate-900">
      <div className="mx-auto flex max-w-md flex-col gap-4 px-5 py-5">
        <header className="rounded-3xl border border-indigo-100 bg-gradient-to-r from-indigo-500 to-violet-500 p-5 text-white shadow-xl">
          <div className="flex items-center gap-3">
            <img
              src="/logo.png"
              alt="Clausea"
              className="h-10 w-10 rounded-2xl bg-white/10 p-1"
            />
            <div>
              <p className="text-xs uppercase tracking-widest text-white/80">
                Clausea Privacy Pulse
              </p>
              <h1 className="text-lg font-semibold">
                Trust what you sign in seconds
              </h1>
            </div>
          </div>
        </header>

        {view === "loading" && <LoadingState />}

        {view === "error" && (
          <FallbackCard
            icon={<XCircle className="h-6 w-6" />}
            title="We couldn’t complete the analysis"
            description={
              error || "Please refresh the page or try again in a moment."
            }
          />
        )}

        {view === "not-found" && (
          <Card>
            <div className="space-y-5 text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                <Shield className="h-7 w-7" />
              </div>
              <div>
                <p className="text-lg font-semibold text-slate-900">
                  Not in our database yet
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  We haven&apos;t analyzed this site yet. Request support and
                  we&apos;ll prioritize it.
                </p>
              </div>

              {supportStatus === "idle" && (
                <button
                  type="button"
                  onClick={handleSupportRequest}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-indigo-500 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:-translate-y-0.5 hover:bg-indigo-600"
                >
                  <BellPlus className="h-4 w-4" />
                  Notify me when it&apos;s ready
                </button>
              )}

              {supportStatus === "loading" && (
                <button
                  type="button"
                  disabled
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-indigo-400 px-4 py-3 text-sm font-semibold text-white shadow-lg"
                >
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Sending request...
                </button>
              )}

              {supportStatus === "success" && (
                <div className="flex flex-col items-center gap-2 rounded-2xl bg-emerald-50 p-4 text-emerald-700">
                  <CheckCircle2 className="h-6 w-6" />
                  <p className="font-medium">Request sent!</p>
                  <p className="text-xs text-emerald-600">
                    We&apos;ll add this site to our priority list.
                  </p>
                </div>
              )}

              {supportStatus === "error" && (
                <div className="flex flex-col items-center gap-2 rounded-2xl bg-rose-50 p-4 text-rose-700">
                  <AlertTriangle className="h-5 w-5" />
                  <p className="text-sm">
                    {supportError || "Something went wrong. Please try again."}
                  </p>
                  <button
                    type="button"
                    onClick={handleSupportRequest}
                    className="text-xs font-semibold underline hover:no-underline"
                  >
                    Try again
                  </button>
                </div>
              )}
            </div>
          </Card>
        )}

        {view === "loaded" && data && (
          <>
            <Card>
              <div className="flex flex-col gap-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm uppercase tracking-wide text-slate-400">
                      Privacy verdict
                    </p>
                    <h2 className="text-2xl font-semibold text-slate-900">
                      {data.product_name}
                    </h2>
                  </div>
                  <div
                    className={`rounded-full border px-3 py-1 text-sm font-semibold ${verdictTone.bg} ${verdictTone.text} ${verdictTone.border}`}
                  >
                    {verdictLabel}
                  </div>
                </div>

                {data.risk_score !== null && (
                  <div>
                    <div className="flex items-center justify-between text-sm text-slate-500">
                      <span>Risk score</span>
                      <span className="font-semibold text-slate-800">
                        {data.risk_score}/10
                      </span>
                    </div>
                    <div className="mt-2 h-2 rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all"
                        style={{ width: `${data.risk_score * 10}%` }}
                      />
                    </div>
                  </div>
                )}

                {data.one_line_summary && (
                  <p className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                    {data.one_line_summary}
                  </p>
                )}
              </div>
            </Card>

            {data.top_concerns && data.top_concerns.length > 0 && (
              <Card title="Top concerns">
                <ol className="space-y-3 text-sm text-slate-600">
                  {data.top_concerns.slice(0, 3).map((concern, index) => (
                    <li key={concern} className="flex gap-2">
                      <TriangleAlert className="mt-1 h-4 w-4 text-amber-500" />
                      <span>{concern}</span>
                    </li>
                  ))}
                </ol>
              </Card>
            )}

            <Card className="bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
              <div className="space-y-3">
                <p className="text-sm uppercase tracking-widest text-white/70">
                  Deep dive
                </p>
                <p className="text-xl font-semibold">
                  See the clause-by-clause analysis
                </p>
                <p className="text-sm text-white/80">
                  Read every policy excerpt, risk rationale, and recommended
                  actions tailored to your use case.
                </p>
                {data.analysis_url && (
                  <button
                    type="button"
                    onClick={() => window.open(data.analysis_url!, "_blank")}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-white/15 px-4 py-3 text-sm font-semibold text-white shadow-lg backdrop-blur transition hover:bg-white/25"
                  >
                    View full report
                    <CheckCircle2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            </Card>
          </>
        )}

        <footer className="pb-2 text-center text-xs text-slate-400">
          Powered by{" "}
          <span className="font-semibold text-slate-600">Clausea AI</span>
        </footer>
      </div>
    </div>
  );
}
