import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const result = await httpJson(`${apiEndpoints.users()}`, {
      method: "POST",
      body,
    });
    return NextResponse.json(result);
  } catch (error) {
    console.error("Error creating user:", error);
    return NextResponse.json(
      { error: `Failed to create user: ${error}` },
      { status: 500 },
    );
  }
}
