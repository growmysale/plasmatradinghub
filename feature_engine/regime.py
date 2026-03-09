"""Regime Detection Engine using Hidden Markov Models.

Classifies market state into: TRENDING_UP, TRENDING_DOWN, RANGING,
VOLATILE_EXPANSION, QUIET_COMPRESSION.

The regime detector is a FILTER, not a signal generator. It tells
strategy agents whether NOW is a good time for THEIR strategy type.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from hmmlearn import hmm

from core.config import get_config
from core.types import Regime

logger = logging.getLogger(__name__)

# Map HMM states to regime labels (assigned after fitting)
REGIME_NAMES = [
    Regime.TRENDING_UP,
    Regime.TRENDING_DOWN,
    Regime.RANGING,
    Regime.VOLATILE_EXPANSION,
    Regime.QUIET_COMPRESSION,
]


class RegimeDetector:
    """Hidden Markov Model based market regime classifier.

    Features fed into HMM:
    - ATR percentile (volatility level)
    - ATR rate of change (expanding/contracting)
    - ADX value (trend strength)
    - Bollinger bandwidth (volatility proxy)
    - Returns autocorrelation (trending=positive, MR=negative)
    - Volume trend
    """

    N_STATES = 5
    MODEL_FILENAME = "regime_hmm.pkl"

    def __init__(self, model_dir: Optional[str] = None):
        config = get_config()
        self.model_dir = Path(model_dir or config.data.models_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model: Optional[hmm.GaussianHMM] = None
        self._load_model()

    def _load_model(self):
        """Load pre-trained model if available."""
        model_path = self.model_dir / self.MODEL_FILENAME
        if model_path.exists():
            try:
                with open(model_path, "rb") as f:
                    self.model = pickle.load(f)
                logger.info("Loaded pre-trained HMM regime model")
            except Exception as e:
                logger.warning(f"Could not load HMM model: {e}")

    def _save_model(self):
        """Save trained model."""
        if self.model:
            model_path = self.model_dir / self.MODEL_FILENAME
            with open(model_path, "wb") as f:
                pickle.dump(self.model, f)
            logger.info(f"Saved HMM model to {model_path}")

    def _prepare_features(self, features_df: pd.DataFrame) -> np.ndarray:
        """Extract HMM input features from feature DataFrame."""
        hmm_cols = [
            "atr_percentile",
            "atr_roc",
            "adx_14",
            "boll_bandwidth",
            "returns_1bar",
            "volume_ratio",
        ]

        available = [c for c in hmm_cols if c in features_df.columns]
        if len(available) < 3:
            logger.warning(f"Only {len(available)} HMM features available, need at least 3")
            return np.array([])

        data = features_df[available].copy()

        # Z-score normalize
        for col in data.columns:
            mean = data[col].mean()
            std = data[col].std()
            if std > 0:
                data[col] = (data[col] - mean) / std
            else:
                data[col] = 0

        data = data.fillna(0).replace([np.inf, -np.inf], 0)
        return data.values

    def fit(self, features_df: pd.DataFrame, n_iter: int = 100):
        """Train the HMM on historical feature data.

        Should be called on 1-2 years of data initially, then
        retrained monthly (walk-forward).
        """
        X = self._prepare_features(features_df)
        if len(X) < 100:
            logger.error("Not enough data to train HMM (need 100+ bars)")
            return

        self.model = hmm.GaussianHMM(
            n_components=self.N_STATES,
            covariance_type="full",
            n_iter=n_iter,
            random_state=42,
            verbose=False,
        )

        try:
            self.model.fit(X)
            logger.info(f"HMM fitted on {len(X)} samples, score={self.model.score(X):.2f}")

            # Label states based on characteristics
            self._label_states(features_df, X)
            self._save_model()

        except Exception as e:
            logger.error(f"HMM training failed: {e}")
            self.model = None

    def _label_states(self, features_df: pd.DataFrame, X: np.ndarray):
        """Assign meaningful labels to HMM states based on their characteristics."""
        if self.model is None:
            return

        states = self.model.predict(X)

        # Analyze each state
        state_chars = {}
        for state in range(self.N_STATES):
            mask = states == state
            if mask.sum() == 0:
                continue

            state_features = features_df.iloc[mask]
            state_chars[state] = {
                "atr_pct": state_features.get("atr_percentile", pd.Series([50])).mean(),
                "adx": state_features.get("adx_14", pd.Series([20])).mean(),
                "returns_mean": state_features.get("returns_1bar", pd.Series([0])).mean(),
                "boll_bw": state_features.get("boll_bandwidth", pd.Series([0.02])).mean(),
                "count": mask.sum(),
            }

        # Sort states by characteristics and map
        if not state_chars:
            return

        # State mapping based on characteristics
        self._state_map = {}
        assigned = set()

        # Highest ADX + positive returns = TRENDING_UP
        sorted_by_adx = sorted(state_chars.items(),
                               key=lambda x: x[1]["adx"] * (1 if x[1]["returns_mean"] > 0 else -1),
                               reverse=True)
        for state, chars in sorted_by_adx:
            if state not in assigned and chars["adx"] > 20 and chars["returns_mean"] > 0:
                self._state_map[state] = Regime.TRENDING_UP
                assigned.add(state)
                break

        # Highest ADX + negative returns = TRENDING_DOWN
        for state, chars in sorted_by_adx:
            if state not in assigned and chars["adx"] > 20 and chars["returns_mean"] <= 0:
                self._state_map[state] = Regime.TRENDING_DOWN
                assigned.add(state)
                break

        # Highest ATR percentile = VOLATILE_EXPANSION
        sorted_by_vol = sorted(state_chars.items(), key=lambda x: x[1]["atr_pct"], reverse=True)
        for state, chars in sorted_by_vol:
            if state not in assigned:
                self._state_map[state] = Regime.VOLATILE_EXPANSION
                assigned.add(state)
                break

        # Lowest ATR percentile = QUIET_COMPRESSION
        sorted_by_vol_asc = sorted(state_chars.items(), key=lambda x: x[1]["atr_pct"])
        for state, chars in sorted_by_vol_asc:
            if state not in assigned:
                self._state_map[state] = Regime.QUIET_COMPRESSION
                assigned.add(state)
                break

        # Remaining = RANGING
        for state in state_chars:
            if state not in assigned:
                self._state_map[state] = Regime.RANGING
                assigned.add(state)

        logger.info(f"HMM state labels: {self._state_map}")

    def predict(self, features_df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Predict regime for each bar.

        Returns:
            regimes: Series of Regime values
            confidences: Series of confidence scores (0-1)
        """
        if self.model is None:
            logger.warning("HMM not trained, returning UNKNOWN regime")
            return (
                pd.Series(Regime.UNKNOWN.value, index=features_df.index),
                pd.Series(0.0, index=features_df.index),
            )

        X = self._prepare_features(features_df)
        if len(X) == 0:
            return (
                pd.Series(Regime.UNKNOWN.value, index=features_df.index),
                pd.Series(0.0, index=features_df.index),
            )

        states = self.model.predict(X)
        probs = self.model.predict_proba(X)

        # Map states to regime names
        state_map = getattr(self, "_state_map", {})
        regime_series = pd.Series(
            [state_map.get(s, Regime.UNKNOWN).value for s in states],
            index=features_df.index,
        )

        confidence_series = pd.Series(
            [probs[i, states[i]] for i in range(len(states))],
            index=features_df.index,
        )

        return regime_series, confidence_series

    def predict_current(self, features_df: pd.DataFrame) -> Tuple[Regime, float]:
        """Get the current regime (latest bar)."""
        regimes, confidences = self.predict(features_df)
        if regimes.empty:
            return Regime.UNKNOWN, 0.0
        return Regime(regimes.iloc[-1]), float(confidences.iloc[-1])

    def get_transition_matrix(self) -> Optional[np.ndarray]:
        """Get the HMM transition probability matrix."""
        if self.model is None:
            return None
        return self.model.transmat_
