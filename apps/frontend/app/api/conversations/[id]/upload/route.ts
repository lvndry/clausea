import { NextRequest, NextResponse } from "next/server";

import { apiEndpoints } from "@lib/config";
import { http } from "@lib/http";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const formData = await request.formData();

    const response = await http(
      `${apiEndpoints.conversations()}/${id}/upload`,
      {
        method: "POST",
        body: formData,
      },
    );

    const result = await response.json();
    return NextResponse.json(result);
  } catch (error) {
    console.error("Error uploading document:", error);
    return NextResponse.json(
      { error: `Failed to upload document: ${error}` },
      { status: 500 },
    );
  }
}
