import { NextRequest, NextResponse } from "next/server";
import { findRequest, patchRequest } from "~~/services/chip/store";

export const dynamic = "force-dynamic";

/** The wallet pressed REJECT. Free the request's nonce and reserved balance right away. */
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const request = findRequest(id);
  if (!request) return NextResponse.json({ error: "unknown request" }, { status: 404 });
  if (request.status !== "pending") {
    return NextResponse.json({ error: `request is ${request.status}`, status: request.status }, { status: 409 });
  }
  const body = await req.json().catch(() => ({}));
  const by = typeof body.by === "string" ? body.by.slice(0, 64) : "device";
  const done = patchRequest(id, { status: "rejected", error: `rejected on ${by}` });
  return NextResponse.json({ status: done.status });
}
