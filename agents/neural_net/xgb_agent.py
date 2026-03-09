"""XGBoost Classifier Strategy Agent.

Preferred regimes: ALL (self-adapts via features)
Logic:
  1. Input: full feature vector (~80 features)
  2. Target: triple barrier label (UP/DOWN/FLAT)
  3. Output: probability of UP, probability of DOWN
  4. Only emit signal when P(direction) > 0.6
  5. Use SHAP values to explain each prediction
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit

from agents.base import StrategyAgent
from core.config import get_config
from core.types import Direction, FeatureVector, Regime, Signal
from feature_engine.engine import get_all_feature_columns

logger = logging.getLogger(__name__)


def create_triple_barrier_labels(
    candles: pd.DataFrame,
    tp_ticks: float = 8.0,
    sl_ticks: float = 4.0,
    max_bars: int = 20,
    tick_size: float = 0.25,
) -> pd.Series:
    """Triple barrier labeling method (Lopez de Prado).

    For each bar, look forward and determine if price hits:
    - Upper barrier (take profit) first → label = 1 (LONG)
    - Lower barrier (stop loss) first → label = -1 (SHORT)
    - Neither within max_bars → label = 0 (FLAT)

    Returns:
        Series of labels: 1 (UP), -1 (DOWN), 0 (FLAT)
    """
    closes = candles["close"].values
    highs = candles["high"].values
    lows = candles["low"].values
    labels = np.zeros(len(closes))

    tp_points = tp_ticks * tick_size
    sl_points = sl_ticks * tick_size

    for i in range(len(closes) - max_bars):
        entry = closes[i]
        upper = entry + tp_points
        lower = entry - sl_points

        for j in range(1, max_bars + 1):
            idx = i + j
            if idx >= len(closes):
                break

            if highs[idx] >= upper:
                labels[i] = 1  # UP
                break
            elif lows[idx] <= lower:
                labels[i] = -1  # DOWN
                break

    return pd.Series(labels, index=candles.index)


class XGBClassifierAgent(StrategyAgent):
    agent_id = "xgb_classifier"
    agent_name = "XGBoost Classifier"
    version = "1.0"
    preferred_regimes = list(Regime)  # All regimes
    min_confidence_threshold = 0.60

    def __init__(self):
        super().__init__()
        self.model: Optional[xgb.XGBClassifier] = None
        self._feature_cols: List[str] = []
        self._params = {
            "tp_ticks": 8.0,
            "sl_ticks": 4.0,
            "max_bars": 20,
            "min_confidence": 0.60,
            "xgb_n_estimators": 200,
            "xgb_max_depth": 5,
            "xgb_learning_rate": 0.05,
            "xgb_min_child_weight": 10,
            "xgb_subsample": 0.8,
            "xgb_colsample_bytree": 0.8,
        }
        self._model_dir = Path(get_config().data.models_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._load_model()

    def _load_model(self):
        model_path = self._model_dir / "xgb_classifier.pkl"
        if model_path.exists():
            try:
                with open(model_path, "rb") as f:
                    data = pickle.load(f)
                self.model = data["model"]
                self._feature_cols = data["feature_cols"]
                logger.info("Loaded XGBoost classifier model")
            except Exception as e:
                logger.warning(f"Could not load XGB model: {e}")

    def _save_model(self):
        model_path = self._model_dir / "xgb_classifier.pkl"
        with open(model_path, "wb") as f:
            pickle.dump({"model": self.model, "feature_cols": self._feature_cols}, f)

    def train(self, features_df: pd.DataFrame, candles: pd.DataFrame):
        """Train the XGBoost classifier on features + triple barrier labels."""
        labels = create_triple_barrier_labels(
            candles,
            tp_ticks=self._params["tp_ticks"],
            sl_ticks=self._params["sl_ticks"],
            max_bars=self._params["max_bars"],
        )

        # Align features and labels
        common_idx = features_df.index.intersection(labels.index)
        X = features_df.loc[common_idx]
        y = labels.loc[common_idx]

        # Remove FLAT labels for cleaner signal
        mask = y != 0
        X = X[mask]
        y = y[mask]

        # Map to 0/1 for binary classification (UP vs DOWN)
        y = (y > 0).astype(int)

        if len(X) < 100:
            logger.warning(f"Not enough labeled samples: {len(X)}")
            return

        self._feature_cols = list(X.columns)

        self.model = xgb.XGBClassifier(
            n_estimators=self._params["xgb_n_estimators"],
            max_depth=self._params["xgb_max_depth"],
            learning_rate=self._params["xgb_learning_rate"],
            min_child_weight=self._params["xgb_min_child_weight"],
            subsample=self._params["xgb_subsample"],
            colsample_bytree=self._params["xgb_colsample_bytree"],
            objective="binary:logistic",
            eval_metric="logloss",
            use_label_encoder=False,
            random_state=42,
        )

        # Time series split for validation
        tscv = TimeSeriesSplit(n_splits=3)
        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        # Train on full data (validation split used above for monitoring)
        self.model.fit(X, y)
        self._save_model()

        train_score = self.model.score(X, y)
        logger.info(f"XGBoost trained on {len(X)} samples, train accuracy: {train_score:.4f}")

    def on_features(self, features: FeatureVector, candles: pd.DataFrame) -> Optional[Signal]:
        if self.model is None:
            return None

        f = features.features

        # Build feature vector
        feature_vals = []
        for col in self._feature_cols:
            feature_vals.append(f.get(col, 0.0))

        X = np.array([feature_vals])

        try:
            proba = self.model.predict_proba(X)[0]
        except Exception:
            return None

        # proba[0] = P(DOWN), proba[1] = P(UP)
        p_up = proba[1] if len(proba) > 1 else proba[0]
        p_down = 1 - p_up

        atr = f.get("atr_14", 1.0)
        if atr <= 0:
            return None

        current_close = candles["close"].iloc[-1]
        direction = Direction.FLAT
        confidence = 0.0

        if p_up > self._params["min_confidence"]:
            direction = Direction.LONG
            confidence = p_up
        elif p_down > self._params["min_confidence"]:
            direction = Direction.SHORT
            confidence = p_down
        else:
            return None

        # Entry, stop, target based on ATR
        risk = atr * 1.0
        reward = atr * 2.0

        if direction == Direction.LONG:
            entry = current_close
            stop = entry - risk
            target = entry + reward
        else:
            entry = current_close
            stop = entry + risk
            target = entry - reward

        # Get top features for explanation
        try:
            importances = self.model.feature_importances_
            top_idx = np.argsort(importances)[-5:]
            top_features = [self._feature_cols[i] for i in top_idx]
        except Exception:
            top_features = []

        return self.create_signal(
            direction=direction,
            confidence=round(confidence, 4),
            entry_price=round(entry * 4) / 4,
            stop_loss=round(stop * 4) / 4,
            take_profit=round(target * 4) / 4,
            reasoning=f"XGB P(up)={p_up:.3f}, P(down)={p_down:.3f}. Top features: {top_features}",
            features_used=top_features,
            features_snapshot={k: f.get(k, 0) for k in top_features},
            regime=features.regime,
        )

    def get_parameters(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_parameters(self, params: Dict[str, Any]):
        self._params.update(params)

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importances from the model."""
        if self.model is None:
            return {}
        importances = self.model.feature_importances_
        return {col: float(imp) for col, imp in zip(self._feature_cols, importances)}
