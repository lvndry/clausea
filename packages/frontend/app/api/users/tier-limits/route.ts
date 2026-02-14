import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function GET(_request: NextRequest) {
  try {
    const data = await httpJson(apiEndpoints.tierLimits());
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching tier limits:", error);
    return NextResponse.json(
      { error: "Failed to fetch tier limits" },
      { status: 500 },
    );
  }
}
