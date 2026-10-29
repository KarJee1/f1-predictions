# F1 Predictions

Unofficial F1 race predictions: an iOS app, the prediction model, and a small backend.

| Folder | What it is |
| --- | --- |
| `app/` | Expo (React Native) iOS app: Home (next race + news), Predictions (race, standings, accuracy), Predict (your own finishing order) |
| `pipeline/` | Python package `f1pred`: data ingestion, features, ranking models, race simulation, explanations, publishing |
| `api/` | FastAPI service that serves the published JSON from Cloud Storage |
| `infra/` | `deploy.sh` sets everything up on Google Cloud's free tier |

## How it works

A Cloud Run job runs hourly on race weekends (twice a day otherwise). Each run:

1. Scores any race that just finished and retrains the models.
2. Predicts the next race at the current stage: before the weekend, after practice, or after qualifying.
3. Publishes the prediction, results, standings (with the predicted change), accuracy history and news as JSON.

The model is a learning-to-rank model (XGBoost or LightGBM, whichever backtests better per stage).
Its scores drive a Monte Carlo simulation (Plackett-Luce with per-driver retirement odds) that gives
each driver's win, podium and points chances and the predicted finishing order. SHAP values explain
each driver's prediction in plain words.

## Running locally

```bash
# pipeline
cd pipeline && python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
pytest
f1pred backfill && f1pred train && f1pred run      # writes to ./.store

# app, against bundled sample data
cd app && npm install && EXPO_PUBLIC_USE_SAMPLE_DATA=1 npx expo start
```

## Data sources

[Jolpica F1](https://github.com/jolpica/jolpica-f1) (results, qualifying, standings),
[OpenF1](https://openf1.org) (practice timing, race weather),
[Open-Meteo](https://open-meteo.com) (forecasts), and publishers' RSS feeds for news.
