"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  width?: number;
  height?: number;
}

export function Logo({ className, width = 24, height = 24 }: LogoProps) {
  return (
    <Image
      src="/static/favicons/logo.png"
      alt="Clausea"
      width={width}
      height={height}
      className={cn("object-contain", className)}
    />
  );
}
