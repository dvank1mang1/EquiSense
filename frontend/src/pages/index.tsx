import { useState } from "react";
import Head from "next/head";
import Layout from "@/components/Layout";
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
        <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">EquiSense</h1>
              <p className="text-slate-400 mt-1">ML-платформа для анализа акций</p>
            </div>
            <TickerSearch onSelect={setSelectedTicker} />
          </div>

          {selectedTicker ? (
            <>
              {/* Overview + Prediction */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                  <StockOverview ticker={selectedTicker} />
                </div>
                <div>
                  <PredictionCard
                    ticker={selectedTicker}
                    model={selectedModel}
                    onModelChange={setSelectedModel}
                  />
                </div>
              </div>

              {/* Price Chart */}
              <div className="card">
                <h2 className="mb-4">График цены</h2>
                <PriceChart ticker={selectedTicker} />
              </div>

              {/* Technical + Fundamental + News */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <TechnicalPanel ticker={selectedTicker} />
                <FundamentalPanel ticker={selectedTicker} />
                <NewsPanel ticker={selectedTicker} />
              </div>

              {/* SHAP Explanation */}
              <div className="card">
                <h2 className="mb-4">Объяснение модели (SHAP)</h2>
                <ShapChart ticker={selectedTicker} model={selectedModel} />
              </div>

              {/* Model Comparison */}
              <div className="card">
                <h2 className="mb-4">Сравнение моделей</h2>
                <ModelComparison ticker={selectedTicker} />
              </div>

              {/* Backtest */}
              <div className="card">
                <h2 className="mb-4">Backtesting</h2>
                <BacktestChart ticker={selectedTicker} model={selectedModel} />
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-32 text-slate-500">
              <p className="text-xl">Выберите тикер для анализа</p>
              <p className="text-sm mt-2">Например: AAPL, MSFT, GOOGL, TSLA</p>
            </div>
          )}
        </div>
      </Layout>
    </>
  );
}
