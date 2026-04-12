import Head from "next/head";
import { useState } from "react";
import { GitCompareArrows } from "lucide-react";
import Layout from "@/components/Layout";
import ActiveTickerBar from "@/components/ActiveTickerBar";
import PageSection from "@/components/PageSection";
import TickerSearch from "@/components/TickerSearch";
import ModelComparison from "@/components/ModelComparison";
import BacktestChart from "@/components/BacktestChart";
import { MODEL_LABELS_LONG, ROLLOUT_MODEL_IDS } from "@/lib/models";
import BrandLogo from "@/components/BrandLogo";
import NewsMarquee from "@/components/NewsMarquee";

export default function ComparePage() {
  const [ticker, setTicker] = useState<string | null>(null);

  return (
    <>
      <Head>
        <title>Сравнение моделей — EquiSense</title>
      </Head>
      <Layout>
        <NewsMarquee focusTicker={ticker} />
        <div className="max-w-7xl mx-auto px-4 py-8 md:py-10 space-y-8 md:space-y-10">
          <header
            className="relative overflow-hidden rounded-2xl border border-surface-700/80 bg-gradient-to-br from-surface-800 via-surface-800/95 to-surface-900/80 px-5 py-6 md:px-8 md:py-8 shadow-lg shadow-black/20"
            aria-labelledby="compare-hero-heading"
          >
            <div
              className="pointer-events-none absolute -right-16 -top-24 h-56 w-56 rounded-full bg-brand-500/10 blur-3xl"
              aria-hidden
            />
            <div
              className="pointer-events-none absolute -bottom-20 -left-10 h-48 w-48 rounded-full bg-emerald-500/5 blur-3xl"
              aria-hidden
            />
            <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0 space-y-3">
                <div className="flex flex-wrap items-center gap-4">
                  <BrandLogo size="lg" glow />
                  <div className="min-w-0 space-y-2">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-brand-400/90">
                      EquiSense
                    </p>
                    <h1
                      id="compare-hero-heading"
                      className="text-3xl md:text-4xl font-bold text-white tracking-tight"
                    >
                      Сравнение моделей
                    </h1>
                  </div>
                </div>
                <p className="text-sm md:text-base text-slate-400 max-w-xl leading-relaxed">
                  Сравнение rollout-моделей (A–F): сигналы, метрики и backtesting на выбранном тикере.
                </p>
              </div>
              <div className="shrink-0 w-full lg:w-auto lg:max-w-md">
                <TickerSearch onSelect={setTicker} />
              </div>
            </div>
          </header>

          {ticker ? (
            <>
              <ActiveTickerBar ticker={ticker} onClear={() => setTicker(null)} />

              <PageSection id="compare-metrics-heading" eyebrow="Сводка" title="ML-метрики и сигналы">
                <ModelComparison ticker={ticker} />
              </PageSection>

              {ROLLOUT_MODEL_IDS.map((model) => (
                <PageSection
                  key={model}
                  id={`compare-backtest-${model}-heading`}
                  eyebrow="Backtesting"
                  title={MODEL_LABELS_LONG[model] ?? model}
                >
                  <BacktestChart ticker={ticker} model={model} />
                </PageSection>
              ))}
            </>
          ) : (
            <section
              className="relative overflow-hidden rounded-2xl border border-dashed border-surface-600/80 bg-surface-800/40 px-6 py-14 md:py-20 text-center"
              aria-labelledby="empty-compare-heading"
            >
              <div
                className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(59,130,246,0.12),transparent_55%)]"
                aria-hidden
              />
              <div className="relative mx-auto flex max-w-lg flex-col items-center gap-5">
                <div
                  className="flex h-14 w-14 items-center justify-center rounded-2xl border border-surface-600 bg-surface-800 text-brand-400 shadow-inner"
                  aria-hidden
                >
                  <GitCompareArrows className="h-7 w-7" strokeWidth={1.5} />
                </div>
                <div className="space-y-2">
                  <h2 id="empty-compare-heading" className="text-xl md:text-2xl font-semibold text-white">
                    Выберите тикер для сравнения
                  </h2>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    После выбора отобразятся метрики по всем rollout-моделям и отдельные графики backtesting для каждой.
                  </p>
                </div>
                <p className="pt-1">
                  <span className="inline-flex items-center rounded-lg border border-brand-500/35 bg-brand-500/10 px-4 py-2.5 text-sm font-medium text-brand-300 shadow-sm transition-colors duration-200">
                    Укажите тикер в поле поиска выше или выберите из списка
                  </span>
                </p>
              </div>
            </section>
          )}
        </div>
      </Layout>
    </>
  );
}
