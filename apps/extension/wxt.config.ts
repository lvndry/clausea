import { defineConfig } from "wxt";

export default defineConfig({
  modules: ["@wxt-dev/module-react"],
  dev: {
    server: {
      port: 3535,
    },
  },
  manifest: {
    name: "Clausea - Privacy Policy Analyzer",
    description:
      "Analyze privacy policies and terms of service with AI. Understand risks, rights, and key terms before you sign up.",
    // Permission justifications:
    // - "activeTab": Required to:
    //   1. Get the current tab URL when popup opens (App.tsx:136, App-new.tsx:167)
    //   2. Listen for tab updates/activation to update extension icon (background.ts:112,119)
    //   3. Set extension icon for specific tabs based on privacy policy verdict (background.ts:56)
    permissions: ["activeTab"],
    // Host permission justifications:
    // - "https://api.clausea.co/*": Production API endpoint for:
    //   1. /extension/check - Check if privacy analysis exists for URL (api.ts:33, background.ts:92,139, App.tsx:190)
    //   2. /extension/domains - Get list of supported domains (api.ts:53)
    //   3. /extension/request-support - Request support for new URL (api.ts:68, App.tsx:221)
    // - "http://localhost:8000/*": Development API endpoint (same endpoints, api.ts:7)
    host_permissions: ["https://api.clausea.co/*", "http://localhost:8000/*"],
    action: {
      default_icon: {
        "16": "icon/16.png",
        "32": "icon/32.png",
        "48": "icon/48.png",
        "128": "icon/128.png",
      },
    },
    icons: {
      "16": "icon/16.png",
      "32": "icon/32.png",
      "48": "icon/48.png",
      "128": "icon/128.png",
    },
  },
});
