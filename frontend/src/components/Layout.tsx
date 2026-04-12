"use client";

import { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import clsx from "clsx";
import BrandLogo from "@/components/BrandLogo";

interface LayoutProps {
  children: ReactNode;
}

function NavLink({ href, children }: { href: string; children: ReactNode }) {
  const { pathname } = useRouter();
  const active = pathname === href;

  return (
    <Link
      href={href}
      className={clsx(
        "rounded-lg px-3 py-2 text-sm font-medium transition-[color,background-color] duration-200 ease-out-soft",
        active
          ? "bg-white/[0.08] text-brand-300 shadow-sm shadow-black/20"
          : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-100",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-900",
      )}
      aria-current={active ? "page" : undefined}
    >
      {children}
    </Link>
  );
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="flex min-h-screen flex-col">
      <nav
        className="sticky top-0 z-50 border-b border-white/[0.06] bg-surface-900/70 shadow-nav backdrop-blur-xl backdrop-saturate-150 supports-[backdrop-filter]:bg-surface-900/55"
        aria-label="Основная навигация"
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 md:px-5">
          <Link
            href="/"
            className="group flex items-center gap-2.5 rounded-lg pr-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-900"
            aria-label="EquiSense — на главную"
          >
            <BrandLogo size="sm" className="transition-opacity group-hover:opacity-95" />
            <span className="text-lg font-bold tracking-tight text-white">
              Equi<span className="text-brand-400">Sense</span>
            </span>
          </Link>
          <div className="flex items-center gap-1 sm:gap-2">
            <NavLink href="/">Дашборд</NavLink>
            <NavLink href="/compare">Сравнение моделей</NavLink>
          </div>
        </div>
      </nav>
      <main className="flex-1">{children}</main>
      <footer className="mt-auto border-t border-white/[0.05] bg-surface-950/80 py-8">
        <div className="mx-auto flex max-w-7xl flex-col items-center gap-4 px-4 text-center">
          <BrandLogo size="sm" className="opacity-90" />
          <div className="space-y-2 text-xs leading-relaxed text-slate-500">
            <p>EquiSense — исследовательский прототип ML-аналитики. Не является инвестиционной рекомендацией.</p>
            <p className="text-slate-600">Данные и прогнозы могут быть неполными или устаревшими.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
