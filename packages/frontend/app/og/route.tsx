import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Clausea AI - Legal Document Intelligence Platform";
export const contentType = "image/png";

export async function GET() {
  try {
    return new ImageResponse(
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "#faf8f4", // Warm ivory: hsl(40, 25%, 97%)
          position: "relative",
        }}
      >
        {/* Main content */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "80px 100px",
            textAlign: "center",
            zIndex: 1,
            maxWidth: "1100px",
          }}
        >
          {/* Brand name */}
          <div
            style={{
              fontSize: "84px",
              fontWeight: "bold",
              color: "#c6704f", // Terracotta
              marginBottom: "40px",
              letterSpacing: "-0.02em",
              lineHeight: "1.1",
              fontFamily: "system-ui, -apple-system, sans-serif",
            }}
          >
            Clausea AI
          </div>

          {/* Main tagline - first part */}
          <div
            style={{
              fontSize: "52px",
              color: "#1a1614", // Deep charcoal: hsl(30, 5%, 10%)
              marginBottom: "12px",
              lineHeight: "1.2",
              fontWeight: "600",
              fontFamily: "system-ui, -apple-system, sans-serif",
            }}
          >
            Legal documents
          </div>

          {/* Italic emphasis line */}
          <div
            style={{
              fontSize: "52px",
              color: "#c6704f", // Terracotta: hsl(18, 55%, 54%)
              marginBottom: "12px",
              lineHeight: "1.2",
              fontWeight: "400",
              fontStyle: "italic",
              fontFamily: "Georgia, serif",
            }}
          >
            were not written for you...
          </div>

          {/* Accent line with underline */}
          <div
            style={{
              fontSize: "52px",
              color: "#6b8e78", // Sage green: hsl(150, 20%, 49%)
              marginBottom: "48px",
              lineHeight: "1.2",
              fontWeight: "600",
              fontFamily: "system-ui, -apple-system, sans-serif",
            }}
          >
            until now
          </div>

          {/* Subtitle */}
          <div
            style={{
              fontSize: "32px",
              color: "#6b5d52", // Muted foreground: hsl(30, 10%, 45%)
              maxWidth: "900px",
              lineHeight: "1.5",
              fontWeight: "400",
              fontFamily: "system-ui, -apple-system, sans-serif",
            }}
          >
            Navigate legal complexities with ease
          </div>
        </div>
      </div>,
      {
        width: 1200,
        height: 630,
      },
    );
  } catch (error) {
    console.error("Error generating OG image:", error);
    // Return a warm-themed fallback
    return new ImageResponse(
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "#faf8f4",
          color: "#c6704f", // Terracotta
          fontSize: "64px",
          fontWeight: "bold",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        Clausea AI
      </div>,
      {
        width: 1200,
        height: 630,
      },
    );
  }
}
