import { describe, expect, it } from "vitest";

import { fireEvent, render, screen } from "@testing-library/react";

import type { ConsumerCase } from "./types";
import { WatchOutFor } from "./watch-out-for";

describe("WatchOutFor citations", () => {
  it("renders the resolved source document and link for verified quotes", () => {
    const cases: ConsumerCase[] = [
      {
        title: "Sells data",
        means_for_you: "Advertisers may receive your activity.",
        severity: "high",
        quote: "sell your personal information",
        quote_status: "from_extraction",
        citation: {
          document_id: "doc-1",
          document_title: "Privacy Policy",
          document_type: "privacy_policy",
          document_url: "https://example.com/privacy",
          quote: "We may sell your personal information to advertisers.",
          section_title: "Section 4",
          verified: true,
        },
      },
    ];

    render(<WatchOutFor cases={cases} />);
    fireEvent.click(screen.getByRole("button", { name: /show me where/i }));

    expect(
      screen.getByText("Source: Privacy Policy - Section 4"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/We may sell your personal information/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open source/i })).toHaveAttribute(
      "href",
      "https://example.com/privacy",
    );
  });

  it("renders all matching source documents when multiple citations exist", () => {
    const cases: ConsumerCase[] = [
      {
        title: "AI training",
        means_for_you: "Your content may train their models.",
        severity: "critical",
        quote: "customer content for model training",
        quote_status: "from_extraction",
        citations: [
          {
            document_id: "doc-privacy",
            document_title: "Privacy Policy",
            document_type: "privacy_policy",
            document_url: "https://example.com/privacy",
            quote:
              "We may use customer content for model training to improve our services.",
            verified: true,
          },
          {
            document_id: "doc-terms",
            document_title: "Terms of Service",
            document_type: "terms_of_service",
            document_url: "https://example.com/terms",
            quote: "We may use customer content for model training.",
            section_title: "Section 8",
            verified: true,
          },
        ],
      },
    ];

    render(<WatchOutFor cases={cases} />);
    fireEvent.click(screen.getByRole("button", { name: /show me where/i }));

    expect(screen.getByText("Source 1: Privacy Policy")).toBeInTheDocument();
    expect(
      screen.getByText("Source 2: Terms of Service - Section 8"),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /open source/i })).toHaveLength(
      2,
    );
  });
});
