"use client";

import { useId } from "react";
import clsx from "clsx";

const SIZES = { sm: 36, md: 40, lg: 52 } as const;

type BrandLogoProps = {
  size?: keyof typeof SIZES;
  className?: string;
  /** Показать мягкое свечение (hero) */
  glow?: boolean;
};

/**
 * Абстрактный знак EquiSense: градиентный квадрат + мини-«график».
 * Не использует внешние картинки — одинаково чётко везде.
 */
export default function BrandLogo({ size = "md", className, glow }: BrandLogoProps) {
  const uid = useId().replace(/:/g, "");
  const dim = SIZES[size];
  const gradId = `es-grad-${uid}`;

  return (
    <span
      className={clsx("relative inline-flex shrink-0", glow && "drop-shadow-[0_0_22px_rgba(34,211,238,0.4)]", className)}
      style={{ width: dim, height: dim }}
      aria-hidden
    >
      <svg width={dim} height={dim} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id={gradId} x1="8" y1="6" x2="34" y2="36" gradientUnits="userSpaceOnUse">
            <stop stopColor="#22d3ee" />
            <stop offset="1" stopColor="#0891b2" />
          </linearGradient>
        </defs>
        <rect x="2" y="2" width="36" height="36" rx="10" fill={`url(#${gradId})`} opacity="0.22" />
        <rect x="4" y="4" width="32" height="32" rx="8" stroke="rgba(34,211,238,0.45)" strokeWidth="1" fill="rgba(11,18,32,0.5)" />
        <path
          d="M11 27 L16.5 20.5 L21 23 L26.5 13 L31 16.5"
          stroke="#e2e8f0"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="31" cy="16.5" r="2.4" fill="#22d3ee" />
      </svg>
    </span>
  );
}
