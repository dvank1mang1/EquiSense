import Head from "next/head";
import { useState } from "react";
import Layout from "@/components/Layout";
import TickerSearch from "@/components/TickerSearch";
import ModelComparison from "@/components/ModelComparison";
import BacktestChart from "@/components/BacktestChart";

export default function ComparePage() {
  const [ticker, setTicker] = useState<string | null>(null);

  return (
    <>
      <Head>
        <title>Сравнение моделей — EquiSense</title>
      </Head>
      <Layout>
        <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1>Сравнение моделей</h1>
              <p className="text-slate-400 mt-1">Model A vs B vs C vs D — метрики и backtesting</p>
            </div>
            <TickerSearch onSelect={setTicker} />
          </div>

          {ticker ? (
            <>
              <div className="card">
                <h2 className="mb-4">ML-метрики и сигналы</h2>
                <ModelComparison ticker={ticker} />
              </div>

              {["model_a", "model_b", "model_c", "model_d"].map((model) => (
                <div key={model} className="card">
                  <h2 className="mb-4">
                    Backtesting — {model.replace("model_", "Model ").toUpperCase()}
                  </h2>
                  <BacktestChart ticker={ticker} model={model} />
                </div>
              ))}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-32 text-slate-500">
              <p className="text-xl">Выберите тикер для сравнения</p>
            </div>
          )}
        </div>
      </Layout>
    </>
  );
}
