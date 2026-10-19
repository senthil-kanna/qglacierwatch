"""Variational quantum circuit (VQC) quantile regressor and matched classical heads.

Circuit (n qubits, L layers, data re-uploading):
    for each layer l:  RY(pi * x_i) on qubit i           (angle encoding, x scaled to [-1, 1])
                       Rot(a, b, c) on every qubit       (3 trainable angles per qubit)
                       CNOT ring i -> i+1 (if entangle)
    readout:           <Z_i> for every qubit -> linear head -> monotone quantile triple

Simulated exactly (analytic expectations, shots=None) on PennyLane default.qubit with backprop
through the state vector. Finite-shot evaluation is available for inference only.
All models share the same monotone head so only the feature map differs.
"""

import math

import pennylane as qml
import torch
from torch import nn


class MonotoneHead(nn.Module):
    """Maps a representation to (q10, q50, q90) with q10 <= q50 <= q90."""

    def __init__(self, n_in: int):
        super().__init__()
        self.lin = nn.Linear(n_in, 3)

    def forward(self, z):
        o = self.lin(z)
        base = o[:, :1]
        inc = nn.functional.softplus(o[:, 1:])
        return torch.cat([base, base + inc[:, :1], base + inc[:, :1] + inc[:, 1:]], dim=1)


def make_circuit(n_qubits: int, layers: int, entangle: bool, shots: int | None = None):
    dev = qml.device("default.qubit", wires=n_qubits)

    @qml.qnode(dev, interface="torch", diff_method="backprop" if shots is None else "parameter-shift", shots=shots)
    def circuit(x, weights):
        for layer in range(layers):
            for i in range(n_qubits):
                qml.RY(math.pi * x[..., i], wires=i)
            for i in range(n_qubits):
                qml.Rot(weights[layer, i, 0], weights[layer, i, 1], weights[layer, i, 2], wires=i)
            if entangle and n_qubits > 1:
                for i in range(n_qubits):
                    qml.CNOT(wires=[i, (i + 1) % n_qubits])
        return [qml.expval(qml.PauliZ(i)) for i in range(n_qubits)]

    return circuit


class VQCRegressor(nn.Module):
    def __init__(self, n_qubits: int, layers: int, entangle: bool):
        super().__init__()
        self.n_qubits, self.layers, self.entangle = n_qubits, layers, entangle
        self.weights = nn.Parameter(0.1 * torch.randn(layers, n_qubits, 3))
        self.circuit = make_circuit(n_qubits, layers, entangle)
        self.head = MonotoneHead(n_qubits)

    def features(self, x, circuit=None):
        out = (circuit or self.circuit)(x, self.weights)
        return torch.stack(list(out), dim=-1).to(torch.float32)

    def forward(self, x):
        return self.head(self.features(x))

    def with_shots(self, shots: int):
        return make_circuit(self.n_qubits, self.layers, self.entangle, shots=shots)

    def circuit_params(self) -> int:
        return self.weights.numel()


class MLPRegressor(nn.Module):
    def __init__(self, n_in: int, hidden: int):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(n_in, hidden), nn.Tanh()) if hidden else nn.Identity()
        self.head = MonotoneHead(hidden or n_in)

    def forward(self, x):
        return self.head(self.body(x))

    def circuit_params(self) -> int:
        return 0


def n_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())
