import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function POST(_request: NextRequest) {
  try {
    const result = await httpJson(
      `${apiEndpoints.users()}/complete-onboarding`,
      {
        method: "POST",
        body: { completed: true },
      },
    );
    return NextResponse.json(result);
  } catch (error) {
    console.error("Error completing onboarding:", error);
    return NextResponse.json(
      { error: `Failed to complete onboarding: ${error}` },
      { status: 500 },
    );
  }
}
