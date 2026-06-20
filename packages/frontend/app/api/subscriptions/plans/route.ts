import { NextResponse } from "next/server";

import { getBackendUrl } from "@/lib/config";
import { httpJson } from "@/lib/http";

interface SubscriptionPlansResponse {
  pro_monthly: string;
  pro_annual: string;
}

export async function GET() {
  try {
    const data = await httpJson<SubscriptionPlansResponse>(
      getBackendUrl("/subscriptions/plans"),
    );

    return NextResponse.json(data, {
      headers: {
        "Cache-Control": "public, max-age=300, stale-while-revalidate=600",
      },
    });
  } catch (error) {
    console.error("Error fetching subscription plans:", error);
    return NextResponse.json(
      { pro_monthly: "", pro_annual: "" },
      { status: 200 },
    );
  }
}
