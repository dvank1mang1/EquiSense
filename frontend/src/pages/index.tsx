import { useState } from "react";
import Head from "next/head";
import Layout from "@/components/Layout";
import ActiveTickerBar from "@/components/ActiveTickerBar";
import PageSection from "@/components/PageSection";
import TickerSearch from "@/components/TickerSearch";
import StockOverview from "@/components/StockOverview";
import PriceChart from "@/components/PriceChart";
import PredictionCard from "@/components/PredictionCard";
import TechnicalPanel from "@/components/TechnicalPanel";
import FundamentalPanel from "@/components/FundamentalPanel";
import NewsPanel from "@/components/NewsPanel";
import BacktestChart from "@/components/BacktestChart";
import ModelComparison from "@/components/ModelComparison";
import ShapChart from "@/components/ShapChart";
import BrandLogo from "@/components/BrandLogo";
import NewsMarquee from "@/components/NewsMarquee";

export default function Home() {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>("model_d");

  return (
    <>
      <Head>
        <title>EquiSense — ML Equity Research Platform</title>
        <meta name="description" content="ML-платформа для анализа и прогнозирования движения акций" />
      </Head>

      <Layout>
        <NewsMarquee focusTicker={selectedTicker} />
        <div className="max-w-7xl mx-auto px-4 py-8 md:py-10 space-y-8 md:space-y-10">
          {/* Hero / header */}
          <header
            className="relative overflow-hidden rounded-2xl border border-surface-700/80 bg-gradient-to-br from-surface-800 via-surface-800/95 to-surface-900/80 px-5 py-6 md:px-8 md:py-8 shadow-lg shadow-black/20"
            aria-labelledby="dashboard-hero-heading"
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
                      id="dashboard-hero-heading"
                      className="text-3xl md:text-4xl font-bold text-white tracking-tight"
                    >
                      Дашборд исследований
                    </h1>
                  </div>
                </div>
                <p className="text-sm md:text-base text-slate-400 max-w-xl leading-relaxed">
                  Прогнозы ML, фундаментал, технический контекст и backtesting — в одном рабочем месте.
                </p>
              </div>
              <div className="shrink-0 w-full lg:w-auto lg:max-w-md">
                <TickerSearch onSelect={setSelectedTicker} />
              </div>
            </div>
          </header>

          {selectedTicker ? (
            <>
              <ActiveTickerBar ticker={selectedTicker} onClear={() => setSelectedTicker(null)} />

              {/* Overview + Prediction */}
              <section
                className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8"
                aria-labelledby="dashboard-summary-heading"
              >
                <h2 id="dashboard-summary-heading" className="sr-only col-span-full">
                  Сводка по тикеру {selectedTicker}
                </h2>
                <div className="lg:col-span-2 min-w-0">
                  <StockOverview key={`overview-${selectedTicker}`} ticker={selectedTicker} />
                </div>
                <div className="min-w-0">
                  <PredictionCard
                    key={`prediction-${selectedTicker}`}
                    ticker={selectedTicker}
                    model={selectedModel}
                    onModelChange={setSelectedModel}
                  />
                </div>
              </section>

              <PageSection id="price-chart-heading" eyebrow="Рынок" title="График цены">
                <PriceChart key={`price-${selectedTicker}`} ticker={selectedTicker} />
              </PageSection>

              {/* Technical + Fundamental + News */}
              <section aria-labelledby="panels-analytics-heading">
                <p className="section-title-accent mb-2">Контекст</p>
                <h2 id="panels-analytics-heading" className="mb-4 text-lg font-semibold tracking-tight text-white md:text-xl">
                  Индикаторы, фундаментал и новости
                </h2>
                <div className="rounded-2xl border border-surface-700/70 bg-surface-900/30 p-4 md:p-5 ring-1 ring-black/20">
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 lg:gap-6">
                    <TechnicalPanel key={`technical-${selectedTicker}`} ticker={selectedTicker} />
                    <FundamentalPanel key={`fundamental-${selectedTicker}`} ticker={selectedTicker} />
                    <NewsPanel key={`news-${selectedTicker}`} ticker={selectedTicker} />
                  </div>
                </div>
              </section>

              <PageSection id="shap-heading" eyebrow="Интерпретация" title="Объяснение модели (SHAP)">
                <ShapChart key={`shap-${selectedTicker}-${selectedModel}`} ticker={selectedTicker} model={selectedModel} />
              </PageSection>

              <PageSection id="model-compare-heading" eyebrow="Качество" title="Сравнение моделей">
                <ModelComparison key={`models-${selectedTicker}`} ticker={selectedTicker} />
              </PageSection>

              <PageSection id="backtest-heading" eyebrow="Стратегия" title="Backtesting">
                <BacktestChart key={`backtest-${selectedTicker}-${selectedModel}`} ticker={selectedTicker} model={selectedModel} />
              </PageSection>
            </>
          ) : (
            <section
              className="relative overflow-hidden rounded-2xl border border-dashed border-surface-600/80 bg-surface-800/40 px-6 py-14 md:py-20 text-center"
              aria-labelledby="empty-dashboard-heading"
            >
              <div
                className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(59,130,246,0.12),transparent_55%)]"
                aria-hidden
              />
              <div className="relative mx-auto flex max-w-lg flex-col items-center gap-5">
                <BrandLogo size="md" className="opacity-95" />
                <div className="space-y-2">
                  <h2 id="empty-dashboard-heading" className="text-xl md:text-2xl font-semibold text-white">
                    Выберите тикер для анализа
                  </h2>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    Введите символ выше или выберите из популярных — откроются котировки, сигнал модели и диагностика.
                  </p>
                </div>
                <p className="text-xs text-slate-500">
                  Примеры:{" "}
                  <span className="font-mono text-slate-400">AAPL</span>,{" "}
                  <span className="font-mono text-slate-400">MSFT</span>,{" "}
                  <span className="font-mono text-slate-400">GOOGL</span>,{" "}
                  <span className="font-mono text-slate-400">TSLA</span>
                </p>
                <p className="pt-1">
                  <span className="inline-flex items-center rounded-lg border border-brand-500/35 bg-brand-500/10 px-4 py-2.5 text-sm font-medium text-brand-300 shadow-sm transition-colors duration-200">
                    Введите тикер в поле поиска вверху или нажмите быстрый выбор
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
