import { describe, expect, it, vi } from "vitest";

// Mock posthog-js before importing analytics
vi.mock("posthog-js", () => ({
  default: {
    identify: vi.fn(),
    capture: vi.fn(),
    reset: vi.fn(),
  },
}));

// Use dynamic import to resolve after mock is set up
const analyticsModule = await import("../analytics");
const {
  identifyUser,
  trackPageView,
  trackUserJourney,
  trackSession,
  trackPerformance,
} = analyticsModule;

// Access the mocked posthog for assertions
const posthog = (await import("posthog-js")).default;

describe("categorizeQuestion (tested via trackUserJourney.questionAsked)", () => {
  // We test the exported categorizeQuestion indirectly through trackUserJourney
  // since it's a private function, but we can also re-export it for testing.
  // For now, test the behavior via the tracking call.

  it("captures question_asked events", () => {
    trackUserJourney.questionAsked("What is the privacy policy?", 30);
    expect(posthog.capture).toHaveBeenCalledWith(
      "question_asked",
      expect.objectContaining({
        question_length: 30,
        question_category: "privacy_policy",
        has_legal_terms: false,
      }),
    );
  });

  it("categorizes terms questions", () => {
    trackUserJourney.questionAsked(
      "What are the terms of service?",
      30,
    );
    expect(posthog.capture).toHaveBeenCalledWith(
      "question_asked",
      expect.objectContaining({
        question_category: "terms_of_service",
      }),
    );
  });

  it("categorizes compliance questions", () => {
    trackUserJourney.questionAsked("Is this GDPR compliant?", 24);
    expect(posthog.capture).toHaveBeenCalledWith(
      "question_asked",
      expect.objectContaining({
        question_category: "compliance",
      }),
    );
  });

  it("categorizes data rights questions", () => {
    trackUserJourney.questionAsked("How do I delete my data?", 25);
    expect(posthog.capture).toHaveBeenCalledWith(
      "question_asked",
      expect.objectContaining({
        question_category: "data_rights",
      }),
    );
  });

  it("categorizes data sharing questions", () => {
    trackUserJourney.questionAsked(
      "Do they share data with third party?",
      36,
    );
    expect(posthog.capture).toHaveBeenCalledWith(
      "question_asked",
      expect.objectContaining({
        question_category: "data_sharing",
      }),
    );
  });

  it("categorizes security questions", () => {
    trackUserJourney.questionAsked("What security measures?", 23);
    expect(posthog.capture).toHaveBeenCalledWith(
      "question_asked",
      expect.objectContaining({
        question_category: "security",
      }),
    );
  });

  it("categorizes general questions", () => {
    trackUserJourney.questionAsked("How does this work?", 19);
    expect(posthog.capture).toHaveBeenCalledWith(
      "question_asked",
      expect.objectContaining({
        question_category: "general",
      }),
    );
  });

  it("detects legal terms in questions", () => {
    trackUserJourney.questionAsked(
      "What about liability and indemnification?",
      40,
    );
    expect(posthog.capture).toHaveBeenCalledWith(
      "question_asked",
      expect.objectContaining({
        has_legal_terms: true,
      }),
    );
  });
});

describe("identifyUser", () => {
  it("calls posthog.identify with user data", () => {
    const user = {
      id: "user_123",
      primaryEmailAddress: { emailAddress: "test@example.com" },
      firstName: "John",
      lastName: "Doe",
      createdAt: "2024-01-01",
      updatedAt: "2024-06-01",
      lastSignInAt: "2024-06-15",
    };

    identifyUser(user);
    expect(posthog.identify).toHaveBeenCalledWith("user_123", {
      email: "test@example.com",
      first_name: "John",
      last_name: "Doe",
      created_at: "2024-01-01",
      updated_at: "2024-06-01",
      last_sign_in_at: "2024-06-15",
    });
  });

  it("does nothing when user is null", () => {
    const callCount = vi.mocked(posthog.identify).mock.calls.length;
    identifyUser(null);
    expect(vi.mocked(posthog.identify).mock.calls.length).toBe(callCount);
  });

  it("does nothing when user is undefined", () => {
    const callCount = vi.mocked(posthog.identify).mock.calls.length;
    identifyUser(undefined);
    expect(vi.mocked(posthog.identify).mock.calls.length).toBe(callCount);
  });
});

describe("trackPageView", () => {
  it("captures page_viewed event", () => {
    trackPageView("Products");
    expect(posthog.capture).toHaveBeenCalledWith("page_viewed", {
      page_name: "Products",
    });
  });

  it("includes additional properties", () => {
    trackPageView("Product Detail", { slug: "test-product" });
    expect(posthog.capture).toHaveBeenCalledWith("page_viewed", {
      page_name: "Product Detail",
      slug: "test-product",
    });
  });
});

describe("trackUserJourney", () => {
  it("tracks onboarding started", () => {
    trackUserJourney.onboardingStarted();
    expect(posthog.capture).toHaveBeenCalledWith("onboarding_started");
  });

  it("tracks sign out and resets posthog", () => {
    trackUserJourney.signOut();
    expect(posthog.capture).toHaveBeenCalledWith("user_signed_out");
    expect(posthog.reset).toHaveBeenCalled();
  });

  it("tracks product viewed", () => {
    trackUserJourney.productViewed("test-slug", "Test Product");
    expect(posthog.capture).toHaveBeenCalledWith("product_viewed", {
      product_slug: "test-slug",
      product_name: "Test Product",
    });
  });

  it("tracks product searched", () => {
    trackUserJourney.productSearched("privacy", 5);
    expect(posthog.capture).toHaveBeenCalledWith("product_searched", {
      search_term: "privacy",
      results_count: 5,
    });
  });
});

describe("trackSession", () => {
  it("tracks session started", () => {
    trackSession.started();
    expect(posthog.capture).toHaveBeenCalledWith("session_started");
  });

  it("tracks session ended with duration", () => {
    trackSession.ended(300);
    expect(posthog.capture).toHaveBeenCalledWith("session_ended", {
      duration_seconds: 300,
    });
  });
});

describe("trackPerformance", () => {
  it("tracks page load time", () => {
    trackPerformance.pageLoad("Dashboard", 1500);
    expect(posthog.capture).toHaveBeenCalledWith("page_load_time", {
      page_name: "Dashboard",
      load_time_ms: 1500,
    });
  });

  it("tracks API call performance", () => {
    trackPerformance.apiCall("/api/products", 250, true);
    expect(posthog.capture).toHaveBeenCalledWith("api_call", {
      endpoint: "/api/products",
      response_time_ms: 250,
      success: true,
    });
  });
});
