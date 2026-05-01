import { NextRequest, NextResponse } from "next/server";

import { getBackendUrl } from "@lib/config";

const VERDICT_LABEL: Record<string, string> = {
  very_user_friendly: "Very user-friendly",
  user_friendly: "User-friendly",
  moderate: "Moderate concerns",
  pervasive: "Pervasive data collection",
  very_pervasive: "Very pervasive data collection",
};

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;

  const res = await fetch(getBackendUrl(`/products/${slug}/overview`), {
    next: { revalidate: 3600 },
  });

  if (!res.ok) {
    return new NextResponse("Not found", { status: 404 });
  }

  const d = await res.json();

  const lines: string[] = [
    `# ${d.product_name} — Privacy Policy Analysis by Clausea AI`,
    "",
    `Risk Score: ${d.risk_score}/10`,
    `Verdict: ${VERDICT_LABEL[d.verdict] ?? d.verdict}`,
    "",
    d.one_line_summary,
    "",
  ];

  if (d.privacy_signals) {
    const s = d.privacy_signals;
    lines.push("## Quick Privacy Signals");
    lines.push(`- Sells data: ${s.sells_data}`);
    lines.push(`- Cross-site tracking: ${s.cross_site_tracking}`);
    lines.push(`- Account deletion: ${s.account_deletion}`);
    lines.push(`- Consent model: ${s.consent_model}`);
    if (s.data_retention_summary) {
      lines.push(`- Data retention: ${s.data_retention_summary}`);
    }
    lines.push("");
  }

  if (d.data_collected?.length) {
    lines.push("## Data Collected");
    for (const item of d.data_collected) lines.push(`- ${item}`);
    lines.push("");
  }

  if (d.third_party_details?.length) {
    lines.push("## Third-Party Sharing");
    for (const t of d.third_party_details) {
      lines.push(
        `- ${t.recipient} (${t.risk_level} risk): ${t.data_shared?.join(", ") ?? ""}`,
      );
    }
    lines.push("");
  }

  if (d.your_rights?.length) {
    lines.push("## Your Rights");
    for (const right of d.your_rights) lines.push(`- ${right}`);
    lines.push("");
  }

  if (d.dangers?.length) {
    lines.push("## Key Concerns");
    for (const danger of d.dangers) lines.push(`- ${danger}`);
    lines.push("");
  }

  if (d.compliance_status && Object.keys(d.compliance_status).length) {
    lines.push("## Compliance");
    for (const [reg, score] of Object.entries(d.compliance_status)) {
      lines.push(`- ${reg}: ${score}/10`);
    }
    lines.push("");
  }

  lines.push(
    `Source: https://clausea.co/products/${slug}`,
    `Analyzed by Clausea AI — https://clausea.co`,
  );

  return new NextResponse(lines.join("\n"), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
    },
  });
}
