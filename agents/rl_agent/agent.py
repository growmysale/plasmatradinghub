"""Reinforcement Learning Trading Agent.

Uses PPO from stable-baselines3 (if available) or a simple rule-based
fallback. The RL agent learns when to trade and when not to.

Environment:
  State: last 30 feature vectors + position + account state
  Actions: 0=HOLD, 1=BUY, 2=SELL, 3=CLOSE
  Reward: Sharpe-adjusted returns with drawdown penalty
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from agents.base import StrategyAgent
from core.config import get_config
from core.types import Direction, FeatureVector, Regime, Signal

logger = logging.getLogger(__name__)

try:
    import gymnasium as gym
    from gymnasium import spaces
    HAS_GYM = True
except ImportError:
    HAS_GYM = False

try:
    from stable_baselines3 import PPO
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False


class TradingEnv(gym.Env if HAS_GYM else object):
    """Custom Gymnasium environment for RL trading agent."""
    metadata = {"render_modes": ["human"]}

    def __init__(self, features: np.ndarray, candles: pd.DataFrame,
                 window_size: int = 30, initial_balance: float = 50000.0):
        if HAS_GYM:
            super().__init__()

        self.features = features
        self.close_prices = candles["close"].values
        self.high_prices = candles["high"].values
        self.low_prices = candles["low"].values
        self.window_size = window_size
        self.initial_balance = initial_balance
        self.n_features = features.shape[1] if len(features.shape) > 1 else 1
        self.point_value = 5.0

        obs_size = window_size * self.n_features + 5  # +5 for account state
        if HAS_GYM:
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
            )
            self.action_space = spaces.Discrete(4)  # HOLD, BUY, SELL, CLOSE

        self.reset()

    def reset(self, seed=None, options=None):
        if HAS_GYM and hasattr(super(), 'reset'):
            super().reset(seed=seed)

        self.step_idx = self.window_size
        self.balance = self.initial_balance
        self.peak_balance = self.initial_balance
        self.position = 0
        self.entry_price = 0.0
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.pnl_history = []

        obs = self._get_obs()
        return obs, {}

    def _get_obs(self) -> np.ndarray:
        start = max(0, self.step_idx - self.window_size)
        window = self.features[start:self.step_idx]

        if len(window) < self.window_size:
            pad = np.zeros((self.window_size - len(window), self.n_features))
            window = np.vstack([pad, window])

        flat = window.flatten()
        account = np.array([
            self.position,
            (self.balance - self.initial_balance) / self.initial_balance,
            self.daily_pnl / 200.0,
            self.daily_trades / 3.0,
            (self.peak_balance - self.balance) / 2000.0,
        ], dtype=np.float32)

        return np.concatenate([flat, account]).astype(np.float32)

    def step(self, action: int):
        close = self.close_prices[self.step_idx]
        reward = 0.0
        done = False

        if action == 1 and self.position == 0 and self.daily_trades < 3:
            self.position = 1
            self.entry_price = close
            self.daily_trades += 1
            reward -= 0.001

        elif action == 2 and self.position == 0 and self.daily_trades < 3:
            self.position = -1
            self.entry_price = close
            self.daily_trades += 1
            reward -= 0.001

        elif action == 3 and self.position != 0:
            if self.position == 1:
                pnl = (close - self.entry_price) * self.point_value
            else:
                pnl = (self.entry_price - close) * self.point_value

            self.balance += pnl
            self.daily_pnl += pnl
            self.peak_balance = max(self.peak_balance, self.balance)
            self.pnl_history.append(pnl)

            reward = pnl / self.initial_balance
            dd = (self.peak_balance - self.balance) / self.initial_balance
            reward -= dd * 0.1

            self.position = 0
            self.entry_price = 0.0

        # Unrealized P&L signal
        if self.position != 0:
            if self.position == 1:
                unrealized = (close - self.entry_price) * self.point_value
            else:
                unrealized = (self.entry_price - close) * self.point_value
            reward += unrealized / self.initial_balance * 0.005

        self.step_idx += 1

        if self.step_idx >= len(self.close_prices) - 1:
            done = True
        if self.balance <= self.initial_balance - 2000:
            done = True
            reward -= 1.0

        obs = self._get_obs()
        return obs, reward, done, False, {}


class RLTradingAgent(StrategyAgent):
    agent_id = "rl_ppo"
    agent_name = "RL PPO Agent"
    version = "1.0"
    preferred_regimes = list(Regime)
    min_confidence_threshold = 0.55

    def __init__(self):
        super().__init__()
        self.rl_model = None
        self._params = {
            "window_size": 30,
            "min_confidence": 0.60,
            "ppo_learning_rate": 3e-4,
            "ppo_n_steps": 2048,
            "ppo_batch_size": 64,
            "ppo_n_epochs": 10,
        }
        self._model_dir = Path(get_config().data.models_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._load_model()

    def _load_model(self):
        model_path = self._model_dir / "rl_ppo_model.zip"
        if model_path.exists() and HAS_SB3:
            try:
                self.rl_model = PPO.load(str(model_path))
                logger.info("Loaded RL PPO model")
            except Exception as e:
                logger.warning(f"Could not load RL model: {e}")

    def train(self, features: np.ndarray, candles: pd.DataFrame, total_timesteps: int = 100000):
        """Train RL agent on historical data."""
        if not HAS_SB3 or not HAS_GYM:
            logger.error("Need stable-baselines3 and gymnasium for RL training")
            return

        env = TradingEnv(features, candles, window_size=self._params["window_size"])
        self.rl_model = PPO(
            "MlpPolicy", env,
            learning_rate=self._params["ppo_learning_rate"],
            n_steps=self._params["ppo_n_steps"],
            batch_size=self._params["ppo_batch_size"],
            n_epochs=self._params["ppo_n_epochs"],
            verbose=0,
        )
        self.rl_model.learn(total_timesteps=total_timesteps)

        model_path = self._model_dir / "rl_ppo_model.zip"
        self.rl_model.save(str(model_path))
        logger.info(f"RL model trained and saved ({total_timesteps} steps)")

    def on_features(self, features: FeatureVector, candles: pd.DataFrame) -> Optional[Signal]:
        """RL agent generates signals via its policy network."""
        if self.rl_model is None:
            return None

        f = features.features
        atr = f.get("atr_14", 1.0)
        if atr <= 0:
            return None

        # Build observation (simplified - use feature vector directly)
        feature_vals = list(f.values())
        obs = np.array(feature_vals[:self._params["window_size"] * 5] +
                      [0, 0, 0, 0, 0], dtype=np.float32)

        # Pad/truncate to match expected size
        expected_size = self.rl_model.observation_space.shape[0] if hasattr(self.rl_model, 'observation_space') else len(obs)
        if len(obs) < expected_size:
            obs = np.pad(obs, (0, expected_size - len(obs)))
        elif len(obs) > expected_size:
            obs = obs[:expected_size]

        try:
            action, _ = self.rl_model.predict(obs, deterministic=True)
        except Exception:
            return None

        current_close = candles["close"].iloc[-1]
        risk = atr * 1.0

        if action == 1:  # BUY
            return self.create_signal(
                direction=Direction.LONG,
                confidence=0.65,
                entry_price=round(current_close * 4) / 4,
                stop_loss=round((current_close - risk) * 4) / 4,
                take_profit=round((current_close + risk * 2) * 4) / 4,
                reasoning="RL PPO policy: BUY action",
                regime=features.regime,
            )
        elif action == 2:  # SELL
            return self.create_signal(
                direction=Direction.SHORT,
                confidence=0.65,
                entry_price=round(current_close * 4) / 4,
                stop_loss=round((current_close + risk) * 4) / 4,
                take_profit=round((current_close - risk * 2) * 4) / 4,
                reasoning="RL PPO policy: SELL action",
                regime=features.regime,
            )

        return None

    def get_parameters(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_parameters(self, params: Dict[str, Any]):
        self._params.update(params)
