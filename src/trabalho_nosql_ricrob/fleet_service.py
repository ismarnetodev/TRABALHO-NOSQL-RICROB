"""Persistência relacional dos dados cadastrais de motoristas e veículos."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEED_MOTORISTAS: tuple[tuple[Any, ...], ...] = (
    (1, "Carlos Andrade", "123456789", "Ativo"),
    (2, "Mariana Silva", "987654321", "Ativo"),
    (3, "Roberto Souza", "456789123", "Em Descanso"),
)

SEED_VEICULOS: tuple[tuple[Any, ...], ...] = (
    (101, "ABC-1A23", "Volvo FH 540", 1),
    (102, "XYZ-9876", "Scania R450", 2),
    (103, "KGB-4567", "Mercedes Actros", 3),
)


@dataclass(frozen=True)
class SQLiteSettings:
    """Parâmetros de conexão com o banco relacional, sem segredos no código."""

    db_path: str = "logitech.db"


class FleetRepository:
    """Encapsula os dados transacionais; coordena motoristas e veículos."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        """Garante as tabelas exigidas antes de qualquer consulta."""
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS motoristas (
                id INTEGER PRIMARY KEY,
                nome TEXT NOT NULL,
                cnh TEXT NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS veiculos (
                id INTEGER PRIMARY KEY,
                placa TEXT NOT NULL UNIQUE,
                modelo TEXT NOT NULL,
                motorista_id INTEGER NOT NULL,
                FOREIGN KEY (motorista_id) REFERENCES motoristas (id)
            );
            """
        )
        self.connection.commit()

    def seed_if_empty(self) -> int:
        """Insere o conjunto demonstrativo uma única vez."""
        cursor = self.connection.execute("SELECT COUNT(*) FROM motoristas")
        if cursor.fetchone()[0] > 0:
            return 0

        self.connection.executemany(
            "INSERT INTO motoristas (id, nome, cnh, status) VALUES (?, ?, ?, ?)",
            SEED_MOTORISTAS,
        )
        self.connection.executemany(
            "INSERT INTO veiculos (id, placa, modelo, motorista_id) VALUES (?, ?, ?, ?)",
            SEED_VEICULOS,
        )
        self.connection.commit()
        return len(SEED_MOTORISTAS) + len(SEED_VEICULOS)

    def list_fleet(self) -> list[dict[str, Any]]:
        """Retorna motorista + veículo já unidos — base para o join poliglota (Módulo 3)."""
        cursor = self.connection.execute(
            """
            SELECT
                m.id AS motorista_id,
                m.nome AS motorista_nome,
                m.status AS motorista_status,
                v.id AS veiculo_id,
                v.placa AS veiculo_placa,
                v.modelo AS veiculo_modelo
            FROM veiculos v
            JOIN motoristas m ON m.id = v.motorista_id
            ORDER BY v.id
            """
        )
        return [dict(row) for row in cursor.fetchall()]

    def status_distribution(self) -> dict[str, int]:
        """Conta motoristas por status — alimenta o gráfico do Módulo 4."""
        cursor = self.connection.execute(
            "SELECT status, COUNT(*) AS total FROM motoristas GROUP BY status"
        )
        return {row["status"]: row["total"] for row in cursor.fetchall()}


def create_fleet_repository(settings: SQLiteSettings | None = None) -> FleetRepository:
    """Conecta, inicializa as tabelas e garante o seed inicial."""
    settings = settings or SQLiteSettings()
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.db_path, check_same_thread=False)
    repository = FleetRepository(connection)
    repository.initialize()
    repository.seed_if_empty()
    return repository