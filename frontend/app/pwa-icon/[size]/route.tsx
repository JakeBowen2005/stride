import { ImageResponse } from "next/og";
import { StrideMark } from "@/components/stride-mark";

const SIZES = new Set([192, 512]);

export async function GET(_req: Request, { params }: { params: Promise<{ size: string }> }) {
  const { size: raw } = await params;
  const size = SIZES.has(Number(raw)) ? Number(raw) : 192;
  return new ImageResponse(<StrideMark size={size} />, { width: size, height: size });
}
