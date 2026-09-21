"""Persistência e consultas geoespaciais de telemetria no MongoDB."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, GEOSPHERE, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from .config import MongoSettings
from .routes import ROUTE_101, ROUTE_102, ROUTE_103, get_next_road_location

SEED_TELEMETRY: tuple[dict[str, Any], ...] = (
    {
        "veiculo_id": 101,
        "location": {"type": "Point", "coordinates": list(ROUTE_101[0])},
        "temperatura": 4.2,
        "velocidade": 65,
        "timestamp": datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
    },
    {
        "veiculo_id": 102,
        "location": {"type": "Point", "coordinates": list(ROUTE_102[0])},
        "temperatura": -18.5,
        "velocidade": 85,
        "timestamp": datetime(2026, 9, 11, 10, 5, tzinfo=UTC),
    },
    {
        "veiculo_id": 103,
        "location": {"type": "Point", "coordinates": list(ROUTE_103[0])},
        "temperatura": 22.0,
        "velocidade": 0,
        "timestamp": datetime(2026, 9, 11, 9, 45, tzinfo=UTC),
    },
)


class TelemetryRepository:
    """Encapsula os dados NoSQL; coordenadas seguem o padrão [longitude, latitude]."""

    def __init__(self, client: MongoClient, settings: MongoSettings | None = None) -> None:
        settings = settings or MongoSettings()
        self.collection: Collection = client[settings.database][settings.collection]

    def initialize(self) -> None:
        """Garante o índice exigido antes de qualquer query geoespacial."""
        self.collection.create_index([("location", GEOSPHERE)], name="location_2dsphere")
        self.collection.create_index(
            [("veiculo_id", ASCENDING), ("timestamp", ASCENDING)],
            name="vehicle_timestamp",
        )

    def seed_if_empty(self) -> int:
        """Insere o conjunto demonstrativo uma única vez."""
        if self.collection.estimated_document_count() > 0:
            return 0
        result = self.collection.insert_many([dict(item) for item in SEED_TELEMETRY])
        return len(result.inserted_ids)

    def reset_telemetry(self) -> int:
        """Limpa as leituras antigas fora da via e recria a carga inicial em vias públicas."""
        self.collection.delete_many({})
        return self.seed_if_empty()

    def find_within_radius(
        self, longitude: float, latitude: float, radius_km: float
    ) -> list[dict[str, Any]]:
        """Retorna registros mais próximos ao ponto de referência, até o raio informado."""
        self._validate_coordinates(longitude, latitude)
        if radius_km <= 0:
            raise ValueError("O raio deve ser maior que zero.")

        query = {
            "location": {
                "$near": {
                    "$geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                    "$maxDistance": radius_km * 1_000,
                }
            }
        }
        return list(self.collection.find(query, {"_id": 0}).limit(500))

    def list_readings(self) -> list[dict[str, Any]]:
        """Retorna todas as leituras armazenadas — base do histórico de temperatura (Módulo 4)."""
        return list(
            self.collection.find({}, {"_id": 0}).sort([("veiculo_id", ASCENDING), ("timestamp", ASCENDING)])
        )

    def find_latest_readings(self) -> dict[int, dict[str, Any]]:
        """Retorna a leitura mais recente por veículo — base do join poliglota (Módulo 3)."""
        latest: dict[int, dict[str, Any]] = {}
        for record in self.collection.find({}, {"_id": 0}).sort("timestamp", -1):
            latest.setdefault(record["veiculo_id"], record)
        return latest

    def simulate_movement(self, step: int = 4) -> int:
        """Cria uma nova leitura por veículo, avançando o veículo ao longo de sua via pública."""
        import random

        latest = self.find_latest_readings()
        documents = []
        for record in latest.values():
            longitude, latitude = record["location"]["coordinates"]
            veiculo_id = record["veiculo_id"]
            new_coords = get_next_road_location(veiculo_id, longitude, latitude, step=step)

            temp_variation = round(random.uniform(-0.5, 0.5), 1)
            new_temp = round(record["temperatura"] + temp_variation, 1)

            speed_variation = random.randint(-5, 5)
            new_speed = max(0, min(110, record["velocidade"] + speed_variation))

            documents.append(
                {
                    **{
                        key: value
                        for key, value in record.items()
                        if key not in {"location", "timestamp", "temperatura", "velocidade"}
                    },
                    "location": {
                        "type": "Point",
                        "coordinates": new_coords,
                    },
                    "temperatura": new_temp,
                    "velocidade": new_speed,
                    "timestamp": datetime.now(UTC),
                }
            )
        return len(self.collection.insert_many(documents).inserted_ids) if documents else 0

    @staticmethod
    def _validate_coordinates(longitude: float, latitude: float) -> None:
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("Coordenadas inválidas: longitude [-180, 180], latitude [-90, 90].")


def create_repository(settings: MongoSettings | None = None) -> TelemetryRepository:
    """Conecta, verifica disponibilidade e inicializa a coleção MongoDB."""
    settings = settings or MongoSettings()
    client = MongoClient(settings.uri, serverSelectionTimeoutMS=settings.server_selection_timeout_ms)
    try:
        client.admin.command("ping")
        repository = TelemetryRepository(client, settings)
        repository.initialize()
        return repository
    except PyMongoError:
        client.close()
        raise