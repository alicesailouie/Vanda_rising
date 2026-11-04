"""Gaussian-process regressors used in two places:

* statistical engine: summer melt forcing -> net seasonal lake-level change;
* water-balance engine: summer melt forcing -> seasonal Onyx River inflow volume.

The Gaussian process uses an RBF + linear (DotProduct) + white-noise kernel. The linear
term matters: with RBF alone, predictions revert to the mean outside the training range,
which would wrongly flatten the response to unprecedented warm summers. Extrapolation is
still the main weakness, so every projection reports the fraction of simulated seasons that
fall outside the observed feature range.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, DotProduct, WhiteKernel
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

Z90 = 1.6448536


def make_gp(n_features: int, seed: int = 0) -> Pipeline:
    kernel = (ConstantKernel(1.0, (1e-3, 1e2)) * RBF(np.ones(n_features), (1e-1, 1e2))
              + ConstantKernel(0.1, (1e-4, 1e2)) * DotProduct(sigma_0=1.0, sigma_0_bounds="fixed")
              + WhiteKernel(0.1, (1e-5, 1e1)))
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=5, random_state=seed)
    return Pipeline([("scale", StandardScaler()), ("gp", gp)])


@dataclass
class LevelModel:
    pipeline: Pipeline
    features: list[str]
    train_min: np.ndarray = field(default_factory=lambda: np.array([]))
    train_max: np.ndarray = field(default_factory=lambda: np.array([]))

    def predict(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        return self.pipeline.predict(X[self.features], return_std=True)

    def outside_training(self, X: pd.DataFrame) -> np.ndarray:
        v = X[self.features].to_numpy(float)
        return ((v < self.train_min) | (v > self.train_max)).any(axis=1)

    def save(self, path) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path) -> "LevelModel":
        return joblib.load(path)


def build_dataset(target: pd.Series, features: pd.DataFrame) -> pd.DataFrame:
    return features.join(target, how="inner").dropna()


def fit(df: pd.DataFrame, features: list[str], target: str = "dlevel_m", seed: int = 0) -> LevelModel:
    X, y = df[features], df[target].to_numpy()
    pipe = make_gp(len(features), seed).fit(X, y)
    v = X.to_numpy(float)
    return LevelModel(pipe, list(features), v.min(axis=0), v.max(axis=0))


def cross_validate(df: pd.DataFrame, features: list[str], target: str = "dlevel_m",
                   seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Leave-one-season-out CV against climatology and linear-regression baselines."""
    X, y = df[features], df[target].to_numpy()
    preds = []
    for i in range(len(df)):
        tr = np.arange(len(df)) != i
        gp = make_gp(len(features), seed).fit(X[tr], y[tr])
        mu, sd = gp.predict(X[~tr], return_std=True)
        lin = LinearRegression().fit(X[tr], y[tr]).predict(X[~tr])
        preds.append({"season": df.index[i], "obs": y[i], "climatology": y[tr].mean(),
                      "linear": lin[0], "gp": mu[0], "gp_sd": sd[0]})
    p = pd.DataFrame(preds).set_index("season")
    metrics = []
    for m in ("climatology", "linear", "gp"):
        err = p[m] - p["obs"]
        metrics.append({"model": m, "rmse_m": float(np.sqrt((err ** 2).mean())), "mae_m": float(err.abs().mean())})
    cov = float(((p["obs"] - p["gp"]).abs() <= Z90 * p["gp_sd"]).mean())
    met = pd.DataFrame(metrics).set_index("model")
    met.loc["gp", "coverage_90"] = cov
    return met, p
