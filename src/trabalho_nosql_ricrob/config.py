"""Configurações do módulo de telemetria."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MongoSettings:
    """Parâmetros de conexão obtidos do ambiente, sem segredos no código."""

    uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    database: str = "geolog_db"
    collection: str = "telemetria"
    server_selection_timeout_ms: int = 5_000

