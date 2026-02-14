import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function GET(_request: NextRequest) {
  try {
    const me = await httpJson(`${apiEndpoints.users()}/me`, { method: "GET" });
    return NextResponse.json(me);
  } catch (error) {
    console.error("Error fetching current user:", error);
    return NextResponse.json(
      { error: `Failed to fetch current user: ${error}` },
      { status: 500 },
    );
  }
}
