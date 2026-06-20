import { NextResponse } from "next/server";

import { subscriptionProxyError } from "@/lib/api/subscription-proxy";
import { getBackendUrl } from "@/lib/config";
import { httpJson } from "@/lib/http";

export async function POST() {
  try {
    const data = await httpJson(getBackendUrl("/subscriptions/pause"), {
      method: "POST",
    });
    return NextResponse.json(data);
  } catch (error) {
    return subscriptionProxyError(error);
  }
}
