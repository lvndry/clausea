import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { httpJson } from "@lib/http";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const conversation = await httpJson(`${apiEndpoints.conversations()}`, {
      method: "POST",
      body,
    });
    return NextResponse.json(conversation);
  } catch (error) {
    console.error("Error creating conversation:", error);
    return NextResponse.json(
      { error: `Failed to create conversation: ${error}` },
      { status: 500 },
    );
  }
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const user_id = searchParams.get("user_id");
    const company_slug = searchParams.get("company_slug");
    const archived = searchParams.get("archived");
    const pinned = searchParams.get("pinned");

    if (!user_id) {
      return NextResponse.json(
        { error: "user_id is required" },
        { status: 400 },
      );
    }

    const query = new URLSearchParams();
    if (company_slug) query.set("company_slug", company_slug);
    if (archived !== null && archived !== undefined)
      query.set("archived", archived);
    if (pinned !== null && pinned !== undefined) query.set("pinned", pinned);

    const url = `${apiEndpoints.conversations()}/user/${user_id}${query.toString() ? `?${query.toString()}` : ""}`;
    const conversations = await httpJson(url, { method: "GET" });
    return NextResponse.json(conversations);
  } catch (error) {
    console.error("Error listing conversations:", error);
    return NextResponse.json(
      { error: `Failed to list conversations: ${error}` },
      { status: 500 },
    );
  }
}
