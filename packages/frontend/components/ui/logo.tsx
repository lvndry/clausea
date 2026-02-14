import Image from "next/image";
import * as React from "react";

interface LogoProps {
  className?: string;
  width?: number;
  height?: number;
}

export function Logo({ className, width = 32, height = 32 }: LogoProps) {
  return (
    <Image
      src="/static/favicons/logo.png"
      alt="Clausea"
      width={width}
      height={height}
      className={className}
    />
  );
}
