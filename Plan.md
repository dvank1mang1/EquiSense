🧠 Project: ML-based Equity Trading Research Platform
📌 Общее описание
Веб-приложение для анализа и прогнозирования движения акций, которое объединяет:
	•	📈 технический анализ
	•	📊 фундаментальные показатели
	•	📰 анализ новостей (NLP / DL)
	•	🤖 несколько ML-моделей
	•	📉 backtesting стратегий
	•	🧾 explainability
👉 система не просто выдает сигнал, а:
	•	прогнозирует вероятность роста
	•	объясняет решение
	•	показывает, как стратегия работала бы на истории

🎯 Цель проекта
Разработать систему, которая:
прогнозирует краткосрочное движение акций на основе комбинирования traditional (technical + fundamental) и alternative data (news sentiment), и оценивает эффективность торговых стратегий.

⚙️ Функциональные требования
1. 📥 Data Ingestion
Система должна:
	•	загружать исторические данные по акциям:
	•	OHLCV (daily)
	•	обновлять данные инкрементально (ежедневно)
	•	получать фундаментальные показатели компаний
	•	получать новости по тикерам

2. 🧱 Data Storage
Система должна:
	•	хранить исторические данные (цены, фундаментал)
	•	хранить новости и sentiment
	•	хранить вычисленные признаки (feature store)
	•	хранить предсказания моделей
	•	хранить результаты backtesting

3. 🧠 Feature Engineering
Система должна автоматически рассчитывать:
Technical features:
	•	returns
	•	volatility
	•	RSI
	•	MACD
	•	moving averages
	•	Bollinger Bands
	•	momentum
Fundamental features:
	•	P/E
	•	EPS
	•	revenue growth
	•	ROE
	•	debt/equity
Alternative data features:
	•	sentiment score (из FinBERT)
	•	news count
	•	positive/negative ratio
	•	sentiment momentum

4. 🤖 ML-модели
Система должна поддерживать несколько моделей:
Обязательные:
	•	Logistic Regression (baseline)
	•	Random Forest
	•	XGBoost / LightGBM (основная модель)
NLP (DL):
	•	FinBERT (ProsusAI/finbert):
	•	анализ новостей в **offline ETL** → Parquet `sentiment` в feature store (см. `README.md`, `ARCHITECTURE_DECISIONS.md` ADR-005)
	•	генерация sentiment features для combined-фрейма моделей C/D

5. 🎯 Prediction Engine
Система должна:
	•	предсказывать вероятность роста акции
	•	генерировать сигнал:
	•	Strong Buy / Buy / Hold / Sell
	•	рассчитывать confidence score

6. 📊 Model Comparison (ключевая фича)
Система должна позволять сравнивать:
	•	Model A: technical only
	•	Model B: technical + fundamental
	•	Model C: technical + news
	•	Model D: all features
👉 вывод:
	•	ML-метрики (F1, ROC-AUC)
	•	trading performance

7. 📉 Backtesting Engine
Система должна:
	•	симулировать торговую стратегию:
	•	based on model predictions
	•	рассчитывать:
	•	cumulative return
	•	Sharpe ratio
	•	max drawdown
	•	win rate

8. 🧾 Explainability
Система должна:
	•	показывать важность признаков
	•	объяснять предсказание:
	•	вклад technical
	•	вклад news
	•	вклад fundamental
(через feature importance / SHAP)

9. 🌐 Web Interface
Пользователь должен иметь возможность:
	•	выбрать тикер
	•	увидеть:
	•	текущую цену
	•	график
	•	предсказание
	•	confidence
	•	посмотреть:
	•	technical indicators
	•	fundamental metrics
	•	новости
	•	увидеть:
	•	объяснение модели
	•	backtest график

10. ⚡ Live Demo
Система должна:
	•	показывать текущую цену (near real-time)
	•	обновлять данные (через API/WebSocket)
👉 только для демонстрации, не core

🧱 Нефункциональные требования
1. Производительность
	•	inference < 1–2 сек
	•	обработка одного тикера в реальном времени

2. Масштабируемость
	•	поддержка 20–50 акций
	•	возможность расширения на большее количество

3. Надежность
	•	кэширование API-запросов
	•	fallback при отсутствии данных

4. Воспроизводимость (очень важно)
	•	фиксированные датасеты для обучения
	•	reproducible backtesting
	•	versioning моделей

5. Модульность
	•	разделение:
	•	data ingestion
	•	feature engineering
	•	ML
	•	backtesting
	•	API

6. Интерпретируемость
	•	обязательное объяснение решений модели

7. Ограничения
	•	не является системой для реальной торговли
	•	не гарантирует прибыль

🧱 Архитектура системы
Frontend (React / Next.js)
        ↓
Backend API (FastAPI)
        ↓
Data Layer:
    - Market Data
    - Fundamentals
    - News

        ↓
Feature Engineering Layer

        ↓
ML Layer:
    - multiple models
    - ensemble logic

        ↓
Backtesting Engine

        ↓
Storage (PostgreSQL + Parquet)

🧰 Технологический стек
Backend
	•	Python
	•	FastAPI
	•	pandas / numpy
ML
	•	scikit-learn
	•	xgboost / lightgbm
	•	shap
NLP / DL
	•	transformers (HuggingFace)
	•	FinBERT
Data APIs
	•	Alpha Vantage (historical + fundamentals)
	•	Finnhub / Polygon (live demo)
	•	news API / RSS
Storage
	•	PostgreSQL
	•	Parquet
Frontend
	•	React / Next.js
	•	Plotly / TradingView
	•	Tailwind CSS

🔥 Ключевые преимущества проекта
	•	сочетание ML + DL + финансы
	•	сравнение fundamental vs alternative data
	•	наличие нескольких моделей
	•	полноценный backtesting
	•	explainable AI
	•	веб-приложение (не просто ноутбук)

💣 Финальный positioning (для защиты)
Можешь сказать буквально так:
Мы разработали модульную ML-платформу для анализа акций, которая объединяет технические, фундаментальные и альтернативные данные. Система использует несколько моделей машинного обучения, включая transformer-based NLP для анализа новостей, и позволяет не только генерировать торговые сигналы, но и оценивать их эффективность с помощью backtesting и объяснять принятые решения.

Если хочешь, следующим шагом могу:
	•	расписать структуру репозитория (как у норм прод проекта)
	•	или дать чёткий план на 10 дней: кто что делает и в каком порядке
