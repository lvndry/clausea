import { NextRequest, NextResponse } from "next/server";

import { subscriptionProxyError } from "@/lib/api/subscription-proxy";
import { getBackendUrl } from "@/lib/config";
import { httpJson } from "@/lib/http";

interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const data = await httpJson<CheckoutResponse>(
      getBackendUrl("/subscriptions/checkout"),
      {
        method: "POST",
        body,
      },
    );

    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    return subscriptionProxyError(error);
  }
}
