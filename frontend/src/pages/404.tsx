import Head from "next/head";
import Link from "next/link";
import { Home, SearchX } from "lucide-react";
import Layout from "@/components/Layout";

export default function NotFoundPage() {
  return (
    <>
      <Head>
        <title>Страница не найдена — EquiSense</title>
      </Head>
      <Layout>
        <div className="mx-auto flex max-w-lg flex-col items-center justify-center px-4 py-20 text-center md:py-28">
          <div
            className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-surface-600 bg-surface-800 text-slate-500"
            aria-hidden
          >
            <SearchX className="h-8 w-8" strokeWidth={1.5} />
          </div>
          <p className="section-title mb-2">404</p>
          <h1 className="text-2xl font-bold tracking-tight text-white md:text-3xl">Такой страницы нет</h1>
          <p className="mt-3 text-sm leading-relaxed text-slate-400">
            Проверьте адрес или вернитесь на дашборд — оттуда доступны анализ тикера и сравнение моделей.
          </p>
          <Link
            href="/"
            className="btn-primary mt-8 inline-flex items-center gap-2 text-sm"
          >
            <Home className="h-4 w-4" aria-hidden />
            На главную
          </Link>
        </div>
      </Layout>
    </>
  );
}
