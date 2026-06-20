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
});
