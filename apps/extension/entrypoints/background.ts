/**
 * Background script for Clausea extension
 *
 * Handles:
 * - Icon color updates based on current tab
 * - Caching of check results
 * - Message passing between popup and content scripts
 */

import {
  checkUrl,
  type ExtensionCheckResponse,
  getVerdictColor,
} from "@/lib/api";

export default defineBackground(() => {
  // Cache for check results (in-memory, cleared on extension restart)
  const cache = new Map<string, ExtensionCheckResponse>();

  // Icon paths for different states
  const iconPaths = {
    safe: {
      16: "/icons/safe/16.png",
      32: "/icons/safe/32.png",
      48: "/icons/safe/48.png",
      128: "/icons/safe/128.png",
    },
    caution: {
      16: "/icons/caution/16.png",
      32: "/icons/caution/32.png",
      48: "/icons/caution/48.png",
      128: "/icons/caution/128.png",
    },
    danger: {
      16: "/icons/danger/16.png",
      32: "/icons/danger/32.png",
      48: "/icons/danger/48.png",
      128: "/icons/danger/128.png",
    },
    gray: {
      16: "/icons/gray/16.png",
      32: "/icons/gray/32.png",
      48: "/icons/gray/48.png",
      128: "/icons/gray/128.png",
    },
  };

  /**
   * Update extension icon based on verdict
   */
  async function updateIcon(
    tabId: number,
    verdict: "safe" | "caution" | "danger" | "gray"
  ) {
    try {
      await chrome.action.setIcon({
        tabId,
        path: iconPaths[verdict],
      });
    } catch (error) {
      // Tab might have been closed
      console.debug("Failed to update icon:", error);
    }
  }

  /**
   * Check URL and update icon
   */
  async function checkAndUpdateIcon(tabId: number, url: string) {
    // Skip non-http URLs
    if (!url.startsWith("http")) {
      await updateIcon(tabId, "gray");
      return;
    }

    // Check cache first
    const domain = new URL(url).hostname;
    const cached = cache.get(domain);

    if (cached) {
      const color = getVerdictColor(cached.verdict) as
        | "safe"
        | "caution"
        | "danger"
        | "gray";
      await updateIcon(tabId, color);
      return;
    }

    // Fetch from API
    try {
      const result = await checkUrl(url);
      cache.set(domain, result);

      if (result.found && result.verdict) {
        const color = getVerdictColor(result.verdict) as
          | "safe"
          | "caution"
          | "danger"
          | "gray";
        await updateIcon(tabId, color);
      } else {
        await updateIcon(tabId, "gray");
      }
    } catch (error) {
      console.error("Failed to check URL:", error);
      await updateIcon(tabId, "gray");
    }
  }

  // Listen for tab updates
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete" && tab.url) {
      checkAndUpdateIcon(tabId, tab.url);
    }
  });

  // Listen for tab activation
  chrome.tabs.onActivated.addListener(async (activeInfo) => {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    if (tab.url) {
      checkAndUpdateIcon(activeInfo.tabId, tab.url);
    }
  });

  // Handle messages from popup
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === "CHECK_URL") {
      const domain = new URL(message.url).hostname;

      // Return cached result if available
      const cached = cache.get(domain);
      if (cached) {
        sendResponse({ success: true, data: cached });
        return true;
      }

      // Fetch from API
      checkUrl(message.url)
        .then((result) => {
          cache.set(domain, result);
          sendResponse({ success: true, data: result });
        })
        .catch((error) => {
          sendResponse({ success: false, error: error.message });
        });

      return true; // Keep channel open for async response
    }

    if (message.type === "CLEAR_CACHE") {
      cache.clear();
      sendResponse({ success: true });
      return true;
    }
  });

  console.log("Clausea background script loaded");
});
