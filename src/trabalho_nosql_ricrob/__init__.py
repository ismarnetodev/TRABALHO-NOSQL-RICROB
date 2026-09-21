from __future__ import annotations

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from pymongo.errors import PyMongoError
from streamlit_folium import st_folium

from trabalho_nosql_ricrob.telemetry_service import create_repository
from trabalho_nosql_ricrob.fleet_service import create_fleet_repository

DEFAULT_LONGITUDE = -34.873
DEFAULT_LATITUDE = -7.115


@st.cache_resource(show_spinner=False)
def get_repository():
    """Mantém uma conexão MongoDB reutilizável durante a sessão Streamlit."""
    return create_repository()


@st.cache_resource(show_spinner=False)
def get_fleet_repository():
    """Mantém uma conexão SQLite reutilizável durante a sessão Streamlit."""
    return create_fleet_repository()


def build_map(longitude: float, latitude: float, radius_km: float, records: list[dict]) -> folium.Map:
    """Constrói o mapa com ponto de referência, área pesquisada e veículos encontrados."""
    map_view = folium.Map(location=[latitude, longitude], zoom_start=12, control_scale=True)
    folium.Circle(
        location=[latitude, longitude], radius=radius_km * 1_000,
        color="#2563eb", fill=True, fill_opacity=0.08, tooltip=f"Raio: {radius_km:.1f} km",
    ).add_to(map_view)
    folium.Marker(
        [latitude, longitude], tooltip="Ponto de referência", icon=folium.Icon(color="blue", icon="info-sign"),
    ).add_to(map_view)
    for record in records:
        record_longitude, record_latitude = record["location"]["coordinates"]
        popup = (
            f"<b>Veículo {record['veiculo_id']}</b><br>"
            f"Temperatura: {record['temperatura']} °C<br>"
            f"Velocidade: {record['velocidade']} km/h<br>"
            f"Leitura: {record['timestamp']}"
        )
        folium.Marker(
            [record_latitude, record_longitude], popup=popup, tooltip=f"Veículo {record['veiculo_id']}",
            icon=folium.Icon(color="red" if record["velocidade"] > 80 else "green"),
        ).add_to(map_view)
    return map_view


def build_fleet_overview(fleet_records: list[dict], latest_readings: dict[int, dict]) -> list[dict]:
    """Cruza em memória os dados cadastrais (SQLite) com a última telemetria (MongoDB)."""
    overview = []
    for item in fleet_records:
        reading = latest_readings.get(item["veiculo_id"])
        overview.append(
            {
                "Motorista": item["motorista_nome"],
                "Status": item["motorista_status"],
                "Placa": item["veiculo_placa"],
                "Modelo": item["veiculo_modelo"],
                "Última Temperatura (°C)": reading["temperatura"] if reading else None,
                "Velocidade (km/h)": reading["velocidade"] if reading else None,
                "Coordenadas": reading["location"]["coordinates"] if reading else None,
                "Última Leitura": reading["timestamp"] if reading else None,
            }
        )
    return overview


def keep_latest_record_per_vehicle(records: list[dict]) -> list[dict]:
    """Mantém apenas a última leitura de cada veículo para a visualização operacional."""
    latest_by_vehicle: dict[int, dict] = {}
    for record in records:
        vehicle_id = record["veiculo_id"]
        current = latest_by_vehicle.get(vehicle_id)
        if current is None or record["timestamp"] > current["timestamp"]:
            latest_by_vehicle[vehicle_id] = record
    return sorted(latest_by_vehicle.values(), key=lambda item: item["veiculo_id"])


def build_kpis(fleet_records: list[dict], latest_readings: dict[int, dict]) -> dict[str, float]:
    """Calcula os indicadores principais do dashboard (Módulo 4)."""
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
    st.set_page_config(page_title="GeoLog | Telemetria", page_icon="🗺️", layout="wide")
    st.title("GeoLog — Geoprocessamento de Telemetria")
    st.caption("MongoDB · GeoJSON · índice 2dsphere · busca geoespacial por raio")

    try:
        repository = get_repository()
        inserted = repository.seed_if_empty()
        if inserted:
            st.success(f"Carga inicial criada com {inserted} registros de telemetria.")
    except PyMongoError as error:
        st.error("Não foi possível conectar ao MongoDB. Configure MONGODB_URI e inicie o servidor.")
        st.exception(error)
        return

    fleet_repository = get_fleet_repository()

    with st.sidebar:
        st.header("Busca por raio")
        longitude = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=DEFAULT_LONGITUDE, format="%.6f")
        latitude = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=DEFAULT_LATITUDE, format="%.6f")
        radius_km = st.slider("Raio de busca (km)", min_value=0.5, max_value=50.0, value=10.0, step=0.5)
        if st.button("Simular movimentação", width="stretch"):
            moved = repository.simulate_movement()
            st.success(f"{moved} nova(s) leitura(s) registrada(s) em vias públicas.")
            st.rerun()

        if st.button("Resetar telemetria em vias públicas", width="stretch"):
            repository.reset_telemetry()
            st.success("Telemetria reiniciada com posições em vias públicas.")
            st.rerun()

    try:
        records = keep_latest_record_per_vehicle(
            repository.find_within_radius(longitude, latitude, radius_km)
        )
    except (PyMongoError, ValueError) as error:
        st.error(f"Falha na consulta geoespacial: {error}")
        return

    st.metric("Veículos encontrados", len(records))
    st_folium(build_map(longitude, latitude, radius_km, records), width=1200, height=560)
    if records:
        st.dataframe(
            [
                {
                    "Veículo": item["veiculo_id"], "Temperatura (°C)": item["temperatura"],
                    "Velocidade (km/h)": item["velocidade"], "Coordenadas": item["location"]["coordinates"],
                    "Timestamp": item["timestamp"],
                }
                for item in records
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Nenhum veículo foi localizado dentro do raio selecionado.")

    st.divider()
    st.subheader("Visão Unificada — Frota (SQLite) × Telemetria (MongoDB)")
    latest_readings = repository.find_latest_readings()
    fleet_overview = build_fleet_overview(fleet_repository.list_fleet(), latest_readings)
    st.dataframe(fleet_overview, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Dashboard Analítico")
    kpis = build_kpis(fleet_repository.list_fleet(), latest_readings)
    kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
    kpi_col1.metric("Frotas Ativas", kpis["frotas_ativas"])
    kpi_col2.metric("Temperatura Média da Carga (°C)", f"{kpis['temperatura_media']:.1f}")
    kpi_col3.metric("Alertas de Velocidade (>80 km/h)", kpis["alertas_velocidade"])

    readings_df = pd.DataFrame(repository.list_readings())
    if not readings_df.empty:
        readings_df["veiculo_id"] = readings_df["veiculo_id"].astype(str)
        temperature_fig = px.line(
            readings_df, x="timestamp", y="temperatura", color="veiculo_id", markers=True,
            title="Histórico de Temperatura por Veículo",
            labels={"timestamp": "Data/Hora", "temperatura": "Temperatura (°C)", "veiculo_id": "Veículo"},
        )
        st.plotly_chart(temperature_fig, width="stretch")

    status_counts = fleet_repository.status_distribution()
    status_df = pd.DataFrame({"Status": list(status_counts.keys()), "Motoristas": list(status_counts.values())})
    status_fig = px.bar(
        status_df, x="Status", y="Motoristas", color="Status",
        title="Distribuição de Status dos Motoristas",
    )
    st.plotly_chart(status_fig, width="stretch")


if __name__ == "__main__":
    main()
