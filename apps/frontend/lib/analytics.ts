import posthog from "posthog-js";

export function identifyUser(user: any) {
  if (!user) return;

  posthog.identify(user.id, {
    email: user.primaryEmailAddress?.emailAddress,
    first_name: user.firstName,
    last_name: user.lastName,
    created_at: user.createdAt,
    updated_at: user.updatedAt,
    last_sign_in_at: user.lastSignInAt,
  });
}

// Page view tracking
export function trackPageView(
  pageName: string,
  properties?: Record<string, any>,
) {
  posthog.capture("page_viewed", {
    page_name: pageName,
    ...properties,
  });
}

// User journey tracking
export const trackUserJourney = {
  // Onboarding
  onboardingStarted() {
    posthog.capture("onboarding_started");
  },

  onboardingCompleted(properties?: Record<string, any>) {
    posthog.capture("onboarding_completed", properties);
  },

  // Authentication
  signIn(method: string) {
    posthog.capture("user_signed_in", { method });
  },

  signUp(method: string) {
    posthog.capture("user_signed_up", { method });
  },

  signOut() {
    posthog.capture("user_signed_out");
    posthog.reset();
  },

  // Product interactions
  productViewed(productSlug: string, productName: string) {
    posthog.capture("product_viewed", {
      product_slug: productSlug,
      product_name: productName,
    });
  },

  productSearched(searchTerm: string, resultsCount: number) {
    posthog.capture("product_searched", {
      search_term: searchTerm,
      results_count: resultsCount,
    });
  },

  // Document uploads
  documentUploadStarted(fileType: string, fileSize: number) {
    posthog.capture("document_upload_started", {
      file_type: fileType,
      file_size: fileSize,
    });
  },

  documentUploadCompleted(
    fileType: string,
    fileSize: number,
    productName: string,
  ) {
    posthog.capture("document_upload_completed", {
      file_type: fileType,
      file_size: fileSize,
      product_name: productName,
    });
  },

  documentUploadFailed(fileType: string, error: string) {
    posthog.capture("document_upload_failed", {
      file_type: fileType,
      error: error,
    });
  },

  // Conversation tracking
  conversationStarted(
    conversationId: string,
    productName: string,
    isNewConversation: boolean,
  ) {
    posthog.capture("conversation_started", {
      conversation_id: conversationId,
      product_name: productName,
      is_new_conversation: isNewConversation,
    });
  },

  // Question tracking
  questionAsked(
    question: string,
    questionLength: number,
    conversationId?: string,
    productSlug?: string,
  ) {
    posthog.capture("question_asked", {
      question_length: questionLength,
      conversation_id: conversationId,
      product_slug: productSlug,
      // Don't capture the full question for privacy, but track patterns
      question_category: categorizeQuestion(question),
      has_legal_terms: containsLegalTerms(question),
    });
  },

  questionAnswered(
    questionLength: number,
    answerLength: number,
    responseTime: number,
    conversationId?: string,
  ) {
    posthog.capture("question_answered", {
      question_length: questionLength,
      answer_length: answerLength,
      response_time_ms: responseTime,
      conversation_id: conversationId,
    });
  },

  questionFailed(error: string, conversationId?: string) {
    posthog.capture("question_failed", {
      error: error,
      conversation_id: conversationId,
    });
  },

  // Feature usage
  featureUsed(featureName: string, properties?: Record<string, any>) {
    posthog.capture("feature_used", {
      feature_name: featureName,
      ...properties,
    });
  },

  // Error tracking
  errorOccurred(
    error: string,
    context: string,
    properties?: Record<string, any>,
  ) {
    posthog.capture("error_occurred", {
      error: error,
      context: context,
      ...properties,
    });
  },
};

// Helper functions for question categorization
function categorizeQuestion(question: string): string {
  const lowerQuestion = question.toLowerCase();

  if (
    lowerQuestion.includes("privacy") ||
    lowerQuestion.includes("data collection")
  ) {
    return "privacy_policy";
  }
  if (lowerQuestion.includes("terms") || lowerQuestion.includes("liability")) {
    return "terms_of_service";
  }
  if (
    lowerQuestion.includes("gdpr") ||
    lowerQuestion.includes("ccpa") ||
    lowerQuestion.includes("compliance")
  ) {
    return "compliance";
  }
  if (
    lowerQuestion.includes("delete") ||
    lowerQuestion.includes("remove") ||
    lowerQuestion.includes("opt out")
  ) {
    return "data_rights";
  }
  if (
    lowerQuestion.includes("share") ||
    lowerQuestion.includes("third party")
  ) {
    return "data_sharing";
  }
  if (lowerQuestion.includes("security") || lowerQuestion.includes("breach")) {
    return "security";
  }

  return "general";
}

function containsLegalTerms(question: string): boolean {
  const legalTerms = [
    "liability",
    "indemnification",
    "warranty",
    "damages",
    "breach",
    "termination",
    "arbitration",
    "governing law",
    "jurisdiction",
    "intellectual property",
    "copyright",
    "trademark",
    "patent",
  ];

  const lowerQuestion = question.toLowerCase();
  return legalTerms.some((term) => lowerQuestion.includes(term));
}

// Session tracking
export const trackSession = {
  started() {
    posthog.capture("session_started");
  },

  ended(duration: number) {
    posthog.capture("session_ended", {
      duration_seconds: duration,
    });
  },
};

// Performance tracking
export const trackPerformance = {
  pageLoad(pageName: string, loadTime: number) {
    posthog.capture("page_load_time", {
      page_name: pageName,
      load_time_ms: loadTime,
    });
  },

  apiCall(endpoint: string, responseTime: number, success: boolean) {
    posthog.capture("api_call", {
      endpoint: endpoint,
      response_time_ms: responseTime,
      success: success,
    });
  },
};

export { posthog };
