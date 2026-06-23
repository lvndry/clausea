import { ImageResponse } from "next/og";
import type { NextRequest } from "next/server";

import { letterGradeToTone } from "@/lib/grade";

export const contentType = "image/png";

// Colors matching lib/grade.ts tone palette
const TONE_COLORS: Record<string, string> = {
  good: "#2B7A5C",
  ok: "#B58D2D",
  warn: "#B58D2D",
  bad: "#BD452D",
};

// Punchy OG-specific labels keyed by verdict
const VERDICT_LABELS: Record<string, { label: string; tone: string }> = {
  very_user_friendly: { label: "Excellent", tone: "good" },
  user_friendly: { label: "Good", tone: "good" },
  moderate: { label: "Mixed", tone: "ok" },
  pervasive: { label: "Concerning", tone: "warn" },
  very_pervasive: { label: "Alarming", tone: "bad" },
};

function normalizeOgGrade(raw: string | null): string | null {
  if (!raw) return null;
  const letter = raw.trim().toUpperCase().charAt(0);
  if (!["A", "B", "C", "D", "E"].includes(letter)) return null;
  return letter;
}

async function loadFont(
  family: string,
  weight: number,
): Promise<ArrayBuffer | null> {
  try {
    const css = await fetch(
      `https://fonts.googleapis.com/css2?family=${encodeURIComponent(family)}:wght@${weight}`,
      { headers: { "User-Agent": "Mozilla/5.0" } },
    ).then((r) => r.text());
    const url = css.match(/src: url\((.+?)\)/)?.[1];
    if (!url) return null;
    return fetch(url).then((r) => r.arrayBuffer());
  } catch {
    return null;
  }
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const name = searchParams.get("name");
  const gradeRaw = searchParams.get("grade");
  const verdict = searchParams.get("verdict") ?? "";

  const isProduct = Boolean(name);

  const [jakartaBold, jakartaMedium] = await Promise.all([
    loadFont("Plus Jakarta Sans", 700),
    loadFont("Plus Jakarta Sans", 500),
  ]);

  type OgFont = {
    name: string;
    data: ArrayBuffer;
    weight?: 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 | 900;
    style?: "normal" | "italic";
  };
  const fonts: OgFont[] = [];
  if (jakartaBold)
    fonts.push({
      name: "Jakarta",
      data: jakartaBold,
      weight: 700,
      style: "normal",
    });
  if (jakartaMedium)
    fonts.push({
      name: "Jakarta",
      data: jakartaMedium,
      weight: 500,
      style: "normal",
    });

  const fontFamily = fonts.length
    ? "Jakarta, sans-serif"
    : "system-ui, -apple-system, sans-serif";

  // ─── Product OG ──────────────────────────────────────────────────────────────
  if (isProduct) {
    const gradeLetter = normalizeOgGrade(gradeRaw);
    const verdictInfo = VERDICT_LABELS[verdict] ?? null;
    const gradeColor = verdictInfo
      ? TONE_COLORS[verdictInfo.tone]
      : gradeLetter
        ? TONE_COLORS[letterGradeToTone(gradeLetter)]
        : "rgba(250,249,246,0.4)";

    return new ImageResponse(
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#1a1918",
          display: "flex",
          flexDirection: "column",
          padding: "56px 64px",
          position: "relative",
          fontFamily,
        }}
      >
        {/* Inset border frame */}
        <div
          style={{
            position: "absolute",
            top: 20,
            left: 20,
            right: 20,
            bottom: 20,
            border: "1px solid rgba(250,249,246,0.1)",
            display: "flex",
          }}
        />

        {/* Top row */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span
            style={{
              color: "#faf9f6",
              fontSize: 18,
              fontWeight: 700,
              letterSpacing: "0.18em",
              fontFamily,
            }}
          >
            CLAUSEA
          </span>
          <span
            style={{
              color: "rgba(250,249,246,0.35)",
              fontSize: 12,
              fontWeight: 500,
              letterSpacing: "0.28em",
              fontFamily,
            }}
          >
            POLICY ANALYSIS
          </span>
        </div>

        {/* Main content row */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 40,
          }}
        >
          {/* Left: company name + verdict */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              flex: 1,
            }}
          >
            <div
              style={{
                fontSize: name && name.length > 14 ? 72 : 96,
                fontWeight: 700,
                color: "#faf9f6",
                lineHeight: 0.9,
                letterSpacing: "-0.03em",
                fontFamily,
                wordBreak: "break-word",
              }}
            >
              {name}
            </div>
            {verdictInfo && (
              <div
                style={{
                  marginTop: 28,
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                }}
              >
                <div
                  style={{
                    width: 3,
                    height: 28,
                    background: gradeColor,
                    display: "flex",
                  }}
                />
                <span
                  style={{
                    color: gradeColor,
                    fontSize: 18,
                    fontWeight: 700,
                    letterSpacing: "0.22em",
                    fontFamily,
                  }}
                >
                  {verdictInfo.label.toUpperCase()}
                </span>
              </div>
            )}
          </div>

          {/* Right: grade letter */}
          {gradeLetter && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                flexShrink: 0,
              }}
            >
              <span
                style={{
                  fontSize: 200,
                  fontWeight: 700,
                  color: gradeColor,
                  lineHeight: 1,
                  letterSpacing: "-0.05em",
                  fontFamily,
                }}
              >
                {gradeLetter}
              </span>
              <span
                style={{
                  color: "rgba(250,249,246,0.25)",
                  fontSize: 11,
                  fontWeight: 500,
                  letterSpacing: "0.28em",
                  fontFamily,
                }}
              >
                PRIVACY GRADE
              </span>
            </div>
          )}
        </div>

        {/* Bottom bar */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderTop: "1px solid rgba(250,249,246,0.1)",
            paddingTop: 24,
          }}
        >
          <span
            style={{
              color: "rgba(250,249,246,0.3)",
              fontSize: 13,
              letterSpacing: "0.22em",
              fontWeight: 500,
              fontFamily,
            }}
          >
            clausea.co
          </span>
          <span
            style={{
              color: "#6b8e78",
              fontSize: 13,
              letterSpacing: "0.22em",
              fontWeight: 700,
              fontFamily,
            }}
          >
            ACTIVE MONITORING
          </span>
        </div>
      </div>,
      { width: 1200, height: 630, fonts },
    );
  }

  // ─── Homepage OG ─────────────────────────────────────────────────────────────
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        background: "#1a1918",
        display: "flex",
        flexDirection: "column",
        padding: "56px 64px",
        position: "relative",
        fontFamily,
      }}
    >
      {/* Inset border frame */}
      <div
        style={{
          position: "absolute",
          top: 20,
          left: 20,
          right: 20,
          bottom: 20,
          border: "1px solid rgba(250,249,246,0.1)",
          display: "flex",
        }}
      />

      {/* Top row */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span
          style={{
            color: "#faf9f6",
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: "0.18em",
            fontFamily,
          }}
        >
          CLAUSEA
        </span>
        <span
          style={{
            color: "rgba(250,249,246,0.35)",
            fontSize: 12,
            fontWeight: 500,
            letterSpacing: "0.28em",
            fontFamily,
          }}
        >
          DOCUMENT INTELLIGENCE
        </span>
      </div>

      {/* Main headline */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          marginTop: 20,
        }}
      >
        <div
          style={{
            fontSize: 96,
            fontWeight: 700,
            color: "#faf9f6",
            lineHeight: 0.88,
            letterSpacing: "-0.03em",
            fontFamily,
          }}
        >
          Privacy Policies
        </div>
        <div
          style={{
            fontSize: 96,
            fontWeight: 700,
            color: "#faf9f6",
            lineHeight: 0.88,
            letterSpacing: "-0.03em",
            marginTop: 8,
            fontFamily,
          }}
        >
          & Terms, Made Easy.
        </div>
        <div
          style={{
            marginTop: 40,
            color: "rgba(250,249,246,0.45)",
            fontSize: 22,
            lineHeight: 1.55,
            maxWidth: 660,
            fontWeight: 500,
            fontFamily,
          }}
        >
          Transforming complex privacy policies and legal agreements into
          plain-language risk signals.
        </div>
      </div>

      {/* Bottom bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderTop: "1px solid rgba(250,249,246,0.1)",
          paddingTop: 24,
        }}
      >
        <span
          style={{
            color: "rgba(250,249,246,0.3)",
            fontSize: 13,
            letterSpacing: "0.22em",
            fontWeight: 500,
            fontFamily,
          }}
        >
          clausea.co
        </span>
        <span
          style={{
            color: "#6b8e78",
            fontSize: 13,
            letterSpacing: "0.22em",
            fontWeight: 700,
            fontFamily,
          }}
        >
          ACTIVE MONITORING
        </span>
      </div>
    </div>,
    { width: 1200, height: 630, fonts },
  );
}
