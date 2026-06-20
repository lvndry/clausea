import { NextResponse } from "next/server";

import { subscriptionProxyError } from "@/lib/api/subscription-proxy";
import { getBackendUrl } from "@/lib/config";
import { httpJson } from "@/lib/http";

export async function GET() {
  try {
    const data = await httpJson(getBackendUrl("/subscriptions/portal"), {
      method: "GET",
    });
    return NextResponse.json(data);
  } catch (error) {
    return subscriptionProxyError(error);
  }
}
