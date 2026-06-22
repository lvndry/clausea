import { NextResponse } from "next/server";

import { getBackendUrl } from "@/lib/config";
import { httpJson } from "@/lib/http";

export const dynamic = "force-dynamic";

interface CheckoutConfigResponse {
  client_token: string;
  environment: string;
}

export async function GET() {
  try {
    const data = await httpJson<CheckoutConfigResponse>(
      getBackendUrl("/subscriptions/checkout-config"),
    );

    return NextResponse.json(data, {
      headers: {
        "Cache-Control": "public, max-age=300, stale-while-revalidate=600",
      },
    });
  } catch (error) {
    console.error("Error fetching checkout config:", error);
    return NextResponse.json(
      { client_token: "", environment: "sandbox" },
      { status: 200 },
    );
  }
}
