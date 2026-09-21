from __future__ import annotations

import os
import random
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from pymongo import ASCENDING, GEOSPHERE, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
from streamlit_folium import st_folium

DEFAULT_LONGITUDE = -34.873
DEFAULT_LATITUDE = -7.115

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

# Coordenadas em vias de Joao Pessoa/PB no formato GeoJSON: [longitude, latitude].
ROUTE_101: list[list[float]] = [
    [-34.878000, -7.120000],
    [-34.875550, -7.118419],
    [-34.873254, -7.119449],
    [-34.870879, -7.120544],
    [-34.866205, -7.120632],
    [-34.861200, -7.121053],
    [-34.855233, -7.121164],
    [-34.848857, -7.121063],
    [-34.841085, -7.121013],
    [-34.835919, -7.121000],
    [-34.832052, -7.119553],
]
ROUTE_102: list[list[float]] = [
    [-34.855228, -7.123003],
    [-34.853309, -7.121151],
    [-34.853363, -7.114544],
    [-34.854820, -7.108472],
    [-34.855631, -7.101941],
    [-34.854503, -7.098785],
    [-34.848225, -7.098214],
    [-34.842872, -7.097802],
    [-34.836896, -7.097375],
    [-34.834623, -7.095350],
    [-34.832697, -7.084774],
]
ROUTE_103: list[list[float]] = [
    [-34.870166, -7.124902],
    [-34.871377, -7.126933],
    [-34.868521, -7.128664],
    [-34.865086, -7.130572],
    [-34.861289, -7.131843],
    [-34.859804, -7.134687],
    [-34.856702, -7.136138],
    [-34.852653, -7.137610],
    [-34.851724, -7.139749],
    [-34.850733, -7.145309],
    [-34.846059, -7.147436],
    [-34.840813, -7.150193],
]
VEHICLE_ROUTES: dict[int, list[list[float]]] = {
    101: ROUTE_101,
    102: ROUTE_102,
    103: ROUTE_103,
}

SEED_TELEMETRY: tuple[dict[str, Any], ...] = (
    {
        "veiculo_id": 101,
        "location": {"type": "Point", "coordinates": ROUTE_101[0]},
        "temperatura": 4.2,
        "velocidade": 65,
        "timestamp": datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
    },
    {
        "veiculo_id": 102,
        "location": {"type": "Point", "coordinates": ROUTE_102[0]},
        "temperatura": -18.5,
        "velocidade": 85,
        "timestamp": datetime(2026, 9, 11, 10, 5, tzinfo=UTC),
    },
    {
        "veiculo_id": 103,
        "location": {"type": "Point", "coordinates": ROUTE_103[0]},
        "temperatura": 22.0,
        "velocidade": 0,
        "timestamp": datetime(2026, 9, 11, 9, 45, tzinfo=UTC),
    },
)


@dataclass(frozen=True)
class MongoSettings:
    uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    database: str = "geolog_db"
    collection: str = "telemetria"
    server_selection_timeout_ms: int = 5_000


@dataclass(frozen=True)
class SQLiteSettings:
    db_path: str = "logitech.db"


class FleetRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
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
        cursor = self.connection.execute(
            "SELECT status, COUNT(*) AS total FROM motoristas GROUP BY status"
        )
        return {row["status"]: row["total"] for row in cursor.fetchall()}


class TelemetryRepository:
    def __init__(self, client: MongoClient, settings: MongoSettings | None = None) -> None:
        settings = settings or MongoSettings()
        self.collection: Collection = client[settings.database][settings.collection]

    def initialize(self) -> None:
        self.collection.create_index([("location", GEOSPHERE)], name="location_2dsphere")
        self.collection.create_index(
            [("veiculo_id", ASCENDING), ("timestamp", ASCENDING)],
            name="vehicle_timestamp",
        )

    def seed_if_empty(self) -> int:
        if self.collection.estimated_document_count() > 0:
            return 0
        result = self.collection.insert_many([dict(item) for item in SEED_TELEMETRY])
        return len(result.inserted_ids)

    def reset_telemetry(self) -> int:
        self.collection.delete_many({})
        return self.seed_if_empty()

    def find_within_radius(
        self, longitude: float, latitude: float, radius_km: float
    ) -> list[dict[str, Any]]:
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("Coordenadas invalidas: longitude [-180, 180], latitude [-90, 90].")
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
        return list(
            self.collection.find({}, {"_id": 0}).sort(
                [("veiculo_id", ASCENDING), ("timestamp", ASCENDING)]
            )
        )

    def find_latest_readings(self) -> dict[int, dict[str, Any]]:
        latest: dict[int, dict[str, Any]] = {}
        for record in self.collection.find({}, {"_id": 0}).sort("timestamp", -1):
            latest.setdefault(record["veiculo_id"], record)
        return latest

    def simulate_movement(self, step: int = 2) -> int:
        latest = self.find_latest_readings()
        documents = []

        for record in latest.values():
            longitude, latitude = record["location"]["coordinates"]
            veiculo_id = record["veiculo_id"]
            new_coords = get_next_road_location(veiculo_id, longitude, latitude, step=step)

            documents.append(
                {
                    "veiculo_id": veiculo_id,
                    "location": {"type": "Point", "coordinates": new_coords},
                    "temperatura": round(record["temperatura"] + random.uniform(-0.5, 0.5), 1),
                    "velocidade": max(0, min(110, record["velocidade"] + random.randint(-5, 5))),
                    "timestamp": datetime.now(UTC),
                }
            )

        return len(self.collection.insert_many(documents).inserted_ids) if documents else 0


def create_fleet_repository(settings: SQLiteSettings | None = None) -> FleetRepository:
    settings = settings or SQLiteSettings()
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.db_path, check_same_thread=False)
    repository = FleetRepository(connection)
    repository.initialize()
    repository.seed_if_empty()
    return repository


def create_repository(settings: MongoSettings | None = None) -> TelemetryRepository:
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


def distance_sq(p1: list[float], p2: list[float]) -> float:
    return (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2


def get_next_road_location(
    veiculo_id: int, current_lon: float, current_lat: float, step: int = 2
) -> list[float]:
    route = VEHICLE_ROUTES.get(veiculo_id, ROUTE_101)
    full_path = route + route[-2:0:-1]
    closest_idx = min(
        range(len(full_path)),
        key=lambda idx: distance_sq([current_lon, current_lat], full_path[idx]),
    )
    return full_path[(closest_idx + step) % len(full_path)]


@st.cache_resource(show_spinner=False)
def get_repository() -> TelemetryRepository:
    return create_repository()


@st.cache_resource(show_spinner=False)
def get_fleet_repository() -> FleetRepository:
    return create_fleet_repository()


def build_map(longitude: float, latitude: float, radius_km: float, records: list[dict]) -> folium.Map:
    map_view = folium.Map(location=[latitude, longitude], zoom_start=12, control_scale=True)
    folium.Circle(
        location=[latitude, longitude],
        radius=radius_km * 1_000,
        color="#2563eb",
        fill=True,
        fill_opacity=0.08,
        tooltip=f"Raio: {radius_km:.1f} km",
    ).add_to(map_view)
    folium.Marker(
        [latitude, longitude],
        tooltip="Ponto de referencia",
        icon=folium.Icon(color="blue", icon="info-sign"),
    ).add_to(map_view)

    for record in records:
        record_longitude, record_latitude = record["location"]["coordinates"]
        popup = (
            f"<b>Veiculo {record['veiculo_id']}</b><br>"
            f"Temperatura: {record['temperatura']} C<br>"
            f"Velocidade: {record['velocidade']} km/h<br>"
            f"Leitura: {record['timestamp']}"
        )
        folium.Marker(
            [record_latitude, record_longitude],
            popup=popup,
            tooltip=f"Veiculo {record['veiculo_id']}",
            icon=folium.Icon(color="red" if record["velocidade"] > 80 else "green"),
        ).add_to(map_view)
    return map_view


def keep_latest_record_per_vehicle(records: list[dict]) -> list[dict]:
    latest_by_vehicle: dict[int, dict] = {}
    for record in records:
        vehicle_id = record["veiculo_id"]
        current = latest_by_vehicle.get(vehicle_id)
        if current is None or record["timestamp"] > current["timestamp"]:
            latest_by_vehicle[vehicle_id] = record
    return sorted(latest_by_vehicle.values(), key=lambda item: item["veiculo_id"])


def build_fleet_overview(fleet_records: list[dict], latest_readings: dict[int, dict]) -> list[dict]:
    overview = []
    for item in fleet_records:
        reading = latest_readings.get(item["veiculo_id"])
        overview.append(
            {
                "Motorista": item["motorista_nome"],
                "Status": item["motorista_status"],
                "Placa": item["veiculo_placa"],
                "Modelo": item["veiculo_modelo"],
                "Ultima Temperatura (C)": reading["temperatura"] if reading else None,
                "Velocidade (km/h)": reading["velocidade"] if reading else None,
                "Coordenadas": reading["location"]["coordinates"] if reading else None,
                "Ultima Leitura": reading["timestamp"] if reading else None,
            }
        )
    return overview


def build_kpis(fleet_records: list[dict], latest_readings: dict[int, dict]) -> dict[str, float]:
    frotas_ativas = sum(1 for item in fleet_records if item["motorista_status"] == "Ativo")
    temperaturas = [reading["temperatura"] for reading in latest_readings.values()]
    temperatura_media = sum(temperaturas) / len(temperaturas) if temperaturas else 0.0
    alertas_velocidade = sum(1 for reading in latest_readings.values() if reading["velocidade"] > 80)
    return {
        "frotas_ativas": frotas_ativas,
        "temperatura_media": temperatura_media,
        "alertas_velocidade": alertas_velocidade,
    }


def main() -> None:
    st.set_page_config(page_title="GeoLog | Telemetria", page_icon="map", layout="wide")
    st.title("GeoLog - Geoprocessamento de Telemetria")
    st.caption("MongoDB, GeoJSON, indice 2dsphere, SQLite e dashboard Streamlit")

    try:
        repository = get_repository()
        inserted = repository.seed_if_empty()
        if inserted:
            st.success(f"Carga inicial criada com {inserted} registros de telemetria.")
    except PyMongoError as error:
        st.error("Nao foi possivel conectar ao MongoDB. Inicie o servidor em localhost:27017.")
        st.exception(error)
        return

    fleet_repository = get_fleet_repository()

    with st.sidebar:
        st.header("Busca por raio")
        longitude = st.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=DEFAULT_LONGITUDE,
            format="%.6f",
        )
        latitude = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=DEFAULT_LATITUDE,
            format="%.6f",
        )
        radius_km = st.slider("Raio de busca (km)", min_value=0.5, max_value=50.0, value=10.0, step=0.5)

        if st.button("Simular movimentacao", width="stretch"):
            moved = repository.simulate_movement()
            st.success(f"{moved} nova(s) leitura(s) registrada(s) em vias publicas.")
            st.rerun()

        if st.button("Resetar telemetria", width="stretch"):
            repository.reset_telemetry()
            st.success("Telemetria reiniciada com posicoes iniciais.")
            st.rerun()

    try:
        records = keep_latest_record_per_vehicle(
            repository.find_within_radius(longitude, latitude, radius_km)
        )
    except (PyMongoError, ValueError) as error:
        st.error(f"Falha na consulta geoespacial: {error}")
        return

    st.metric("Veiculos encontrados", len(records))
    st_folium(build_map(longitude, latitude, radius_km, records), width=1200, height=560)

    if records:
        st.dataframe(
            [
                {
                    "Veiculo": item["veiculo_id"],
                    "Temperatura (C)": item["temperatura"],
                    "Velocidade (km/h)": item["velocidade"],
                    "Coordenadas": item["location"]["coordinates"],
                    "Timestamp": item["timestamp"],
                }
                for item in records
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Nenhum veiculo foi localizado dentro do raio selecionado.")

    st.divider()
    st.subheader("Visao Unificada - Frota SQLite x Telemetria MongoDB")
    latest_readings = repository.find_latest_readings()
    fleet_records = fleet_repository.list_fleet()
    st.dataframe(
        build_fleet_overview(fleet_records, latest_readings),
        width="stretch",
        hide_index=True,
    )

    st.divider()
    st.subheader("Dashboard Analitico")
    kpis = build_kpis(fleet_records, latest_readings)
    kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
    kpi_col1.metric("Frotas Ativas", kpis["frotas_ativas"])
    kpi_col2.metric("Temperatura Media da Carga (C)", f"{kpis['temperatura_media']:.1f}")
    kpi_col3.metric("Alertas de Velocidade (>80 km/h)", kpis["alertas_velocidade"])

    readings_df = pd.DataFrame(repository.list_readings())
    if not readings_df.empty:
        readings_df["veiculo_id"] = readings_df["veiculo_id"].astype(str)
        temperature_fig = px.line(
            readings_df,
            x="timestamp",
            y="temperatura",
            color="veiculo_id",
            markers=True,
            title="Historico de Temperatura por Veiculo",
            labels={
                "timestamp": "Data/Hora",
                "temperatura": "Temperatura (C)",
                "veiculo_id": "Veiculo",
            },
        )
        st.plotly_chart(temperature_fig, width="stretch")

    status_counts = fleet_repository.status_distribution()
    status_df = pd.DataFrame({"Status": list(status_counts.keys()), "Motoristas": list(status_counts.values())})
    status_fig = px.bar(
        status_df,
        x="Status",
        y="Motoristas",
        color="Status",
        title="Distribuicao de Status dos Motoristas",
    )
    st.plotly_chart(status_fig, width="stretch")


if __name__ == "__main__":
    main()
