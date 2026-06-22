import { describe, expect, it } from "vitest";

import { render, screen } from "@testing-library/react";

import { ComplianceBadges } from "./compliance-badges";

describe("ComplianceBadges", () => {
  it("shows evidence-backed rationale with letter grade", () => {
    render(
      <ComplianceBadges
        compliance={{
          GDPR: {
            score: 7,
            status: "Partially Compliant",
            assessment_notes:
              "Privacy Policy and DPA cover EU rights and SCC transfers.",
            strengths: ["Lawful basis for processing stated in Privacy Policy"],
            gaps: ["No specific retention periods for account data"],
          },
        }}
      />,
    );

    expect(screen.getByText("GDPR")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Privacy Policy and DPA cover EU rights and SCC transfers.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Lawful basis for processing stated in Privacy Policy"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No specific retention periods for account data"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/No detailed assessment notes available/i),
    ).not.toBeInTheDocument();
  });

  it("shows insufficient evidence instead of letter grade when only scores exist", () => {
    render(
      <ComplianceBadges
        complianceStatus={{
          GDPR: 7,
          CCPA: 6,
        }}
      />,
    );

    expect(screen.getAllByText("Insufficient evidence")).toHaveLength(2);
    expect(screen.queryByText("B")).not.toBeInTheDocument();
    expect(
      screen.getAllByText(/evidence-backed assessment notes yet/i),
    ).toHaveLength(2);
  });

  it("prefers justified compliance over bare compliance_status scores", () => {
    render(
      <ComplianceBadges
        compliance={{
          GDPR: {
            score: 7,
            status: "Partially Compliant",
            assessment_notes: "Based on Privacy Policy.",
            strengths: ["EU rights described"],
            gaps: ["DPO contact missing"],
          },
        }}
        complianceStatus={{ GDPR: 5, CCPA: 6 }}
      />,
    );

    expect(screen.getByText("B")).toBeInTheDocument();
    expect(screen.getByText("Based on Privacy Policy.")).toBeInTheDocument();
    expect(screen.getByText("CCPA")).toBeInTheDocument();
    expect(screen.getAllByText("Insufficient evidence")).toHaveLength(1);
  });
});
