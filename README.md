# ⚽ Football Match Prediction using Elo & Poisson

A Data Science & MLOps–focused project

This project builds a probabilistic football match prediction system using classical statistical models:
* Elo ratings → team strength & 1X2 probabilities
* Poisson goal model → expected goals, Over/Under, BTTS, scoreline distributions

The system is designed as a production-style ML service with:
* reproducible training
* Database-backed state (ratings & matches)
* API-based inference
* Deployable architecture (local → cloud)

⸻

## 🎯 Project goal

The objective is not to predict exact scores, but to:
*	model relative team strength
* estimate goal distributions
* produce well-calibrated probabilities for football markets

This mirrors how real-world sports analytics and betting models are built.



## 🧠 Modeling approach

1️⃣ Elo rating model (team strength)

Each team has a latent rating representing its strength.

Core ideas:
* beating strong teams increases rating more
* losing to weak teams decreases rating more
* ratings are updated sequentially from match results

From the Elo difference between two teams we derive:
* P(Home win)
* P(Draw)
* P(Away win)

This forms the baseline predictive model.

Why Elo?
* interpretable
* robust with limited data
* widely used in competitive systems (chess, football, esports)


## 2️⃣ Poisson goal model (goal counts)

Goals are modeled as rare events over fixed time → ideal for Poisson processes.

For each match we estimate:
# _home = expected home goals
# λ_away = expected away goals

From these lambdas we construct a joint score probability matrix:

This matrix allows us to compute:
*	Over 2.5 goals
* BTTS (Both Teams To Score)
* Most likely scorelines
* Total probability mass captured

Why Poisson?
*	mathematically grounded
* interpretable
* standard in football analytics literature

## 🗂️ Data & feature pipeline

Data source
*	Match data fetched from football-data.org API
* Only finished matches are used for training
* Upcoming fixtures are used only for inference

Storage
* SQLite database

Feature usage
* Historical match outcomes
* Team IDs (stable across seasons)
* No manual feature engineering (intentionally)

This keeps the system simple, explainable, and reproducible.


## 🔁 Training workflow (MLOps perspective)

Training = two stages

1. Data ingestion
* Fetch finished matches
* Upsert into local database
* Handles API rate limits gracefully

2. Model rebuild
* Recompute Elo ratings from DB state
* No dependency on external APIs at inference time

This separation allows:
* retraining without re-fetching data
* resilience to upstream failures


## 📡 API as a model-serving layer

The FastAPI service acts as a model inference API, not a CRUD backend.


⚙️ Deployment & reproducibility
*Frontend(netlify)
*Backend(Render)

Configuration via environment variables
* API tokens
* training league selection
* CORS origins


📊 Model limitations & design choices

Known limitations
* Poisson assumes independent goal events
* No player-level features
* real-time lineups or injuries

Intentional decisions
* Avoid black-box ML models
* Prioritize interpretability
* Keep retraining cheap and fast


