"""Quantile LSTM (PyTorch) trained with the pinball loss on standardised log discharge.

Input: the last seq_len days of availability-shifted daily variables (SEQ_COLS) ending at the
issue date, plus the target date's season. Output: P10, P50, P90 built as base + cumulative
softplus increments, so quantiles cannot cross by construction.

Normalisation statistics come from training rows only. Early stopping uses the final 365 days of
the training period (inner hold-out), never the calibration or test periods.
"""

import time

import numpy as np
import pandas as pd
import torch
from torch import nn

from src.features.build import SEQ_COLS

QUANTILES = (0.1, 0.5, 0.9)


class _Net(nn.Module):
    def __init__(self, n_in: int, n_static: int, hidden: int, layers: int, dropout: float):
        super().__init__()
        self.lstm = nn.LSTM(n_in, hidden, num_layers=layers, batch_first=True, dropout=dropout if layers > 1 else 0.0)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Sequential(nn.Linear(hidden + n_static, hidden), nn.ReLU(), nn.Linear(hidden, 3))

    def forward(self, seq, static):
        out, _ = self.lstm(seq)
        z = self.head(torch.cat([self.drop(out[:, -1]), static], dim=1))
        base = z[:, :1]
        inc = nn.functional.softplus(z[:, 1:])
        return torch.cat([base, base + inc[:, :1], base + inc[:, :1] + inc[:, 1:]], dim=1)


def pinball_loss(pred: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    taus = torch.tensor(QUANTILES, dtype=pred.dtype, device=pred.device)
    d = y[:, None] - pred
    return torch.maximum(taus * d, (taus - 1) * d).mean()


class QuantileLSTM:
    name = "quantile_lstm"

    def __init__(self, params: dict, seq_len: int = 60, batch_size: int = 128, patience: int = 8, seed: int = 0):
        self.params = params
        self.seq_len = seq_len
        self.batch_size = batch_size
        self.patience = patience
        self.seed = seed

    # -- data ------------------------------------------------------------------------------
    def _arrays(self, table: pd.DataFrame, idx: pd.DatetimeIndex):
        pos = table.index.get_indexer(idx)
        L = self.seq_len
        padded = np.vstack([np.zeros((L - 1, self.A.shape[1]), np.float32), self.A])
        seq = np.stack([padded[p : p + L] for p in pos])  # rows p-L+1..p of the original table
        tdoy = (idx + pd.Timedelta(days=self.h)).dayofyear.to_numpy()
        static = np.column_stack([np.sin(2 * np.pi * tdoy / 365.25), np.cos(2 * np.pi * tdoy / 365.25)]).astype(np.float32)
        return torch.from_numpy(seq), torch.from_numpy(static)

    def fit(self, table: pd.DataFrame, h: int, train_idx: pd.DatetimeIndex, **_) -> "QuantileLSTM":
        torch.manual_seed(self.seed)
        torch.set_num_threads(4)
        self.h = h
        train_rows = table.loc[train_idx, SEQ_COLS]
        self.mu = train_rows.mean().to_numpy(np.float32)
        self.sd = train_rows.std().replace(0, 1).to_numpy(np.float32)
        self.A = np.nan_to_num(((table[SEQ_COLS].to_numpy(np.float32) - self.mu) / self.sd), nan=0.0)

        y = table.loc[train_idx, f"y_h{h}"]
        keep = y.notna().to_numpy()
        idx, logy = train_idx[keep], np.log(y[keep].to_numpy())
        self.y_mu, self.y_sd = float(logy.mean()), float(logy.std())
        yz = torch.tensor((logy - self.y_mu) / self.y_sd, dtype=torch.float32)

        # Inner hold-out for early stopping: the last 365 issue dates of the training period, with
        # an h-day gap so their targets do not overlap the fitted samples.
        cut = idx.max() - pd.Timedelta(days=365)
        fit_m = idx <= cut - pd.Timedelta(days=h)
        es_m = idx > cut
        seq, static = self._arrays(table, idx)
        p = self.params
        self.net = _Net(seq.shape[2], static.shape[1], p["hidden"], p["layers"], p["dropout"])
        opt = torch.optim.Adam(self.net.parameters(), lr=p["lr"])
        fi = np.where(fit_m)[0]
        ei = np.where(es_m)[0]
        best, best_state, wait = np.inf, None, 0
        t0 = time.perf_counter()
        gen = np.random.default_rng(self.seed)
        for epoch in range(p["epochs"]):
            self.net.train()
            gen.shuffle(fi)
            for b in range(0, len(fi), self.batch_size):
                bi = fi[b : b + self.batch_size]
                opt.zero_grad()
                loss = pinball_loss(self.net(seq[bi], static[bi]), yz[bi])
                loss.backward()
                nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                opt.step()
            self.net.eval()
            with torch.no_grad():
                val = float(pinball_loss(self.net(seq[ei], static[ei]), yz[ei]))
            if val < best - 1e-5:
                best, wait = val, 0
                best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
                self.best_epoch = epoch + 1
            else:
                wait += 1
                if wait >= self.patience:
                    break
        if best_state is not None:  # None only if the hold-out loss was never finite
            self.net.load_state_dict(best_state)
        self.train_seconds = time.perf_counter() - t0
        return self

    def predict(self, table: pd.DataFrame, idx: pd.DatetimeIndex) -> np.ndarray:
        seq, static = self._arrays(table, idx)
        self.net.eval()
        with torch.no_grad():
            z = self.net(seq, static).numpy()
        return np.exp(z * self.y_sd + self.y_mu)

    def n_params(self) -> int:
        return sum(p.numel() for p in self.net.parameters())
