import { ReactNode } from "react";
import Link from "next/link";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-surface-900">
      <nav className="border-b border-surface-700 bg-surface-800">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="text-xl font-bold text-brand-500">
            EquiSense
          </Link>
          <div className="flex gap-6 text-sm text-slate-400">
            <Link href="/" className="hover:text-white transition-colors">Dashboard</Link>
            <Link href="/compare" className="hover:text-white transition-colors">Сравнение моделей</Link>
          </div>
        </div>
      </nav>
      <main>{children}</main>
    </div>
  );
}
