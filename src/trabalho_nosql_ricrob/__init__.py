"""GeoLog: módulo de geoprocessamento e telemetria MongoDB."""

from __future__ import annotations

import folium
import streamlit as st
from pymongo.errors import PyMongoError
from streamlit_folium import st_folium

from trabalho_nosql_ricrob.telemetry_service import create_repository

DEFAULT_LONGITUDE = -34.873
DEFAULT_LATITUDE = -7.115


@st.cache_resource(show_spinner=False)
def get_repository():
    """Mantém uma conexão MongoDB reutilizável durante a sessão Streamlit."""
    return create_repository()


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

    with st.sidebar:
        st.header("Busca por raio")
        longitude = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=DEFAULT_LONGITUDE, format="%.6f")
        latitude = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=DEFAULT_LATITUDE, format="%.6f")
        radius_km = st.slider("Raio de busca (km)", min_value=0.5, max_value=50.0, value=10.0, step=0.5)
        if st.button("Simular movimentação", use_container_width=True):
            moved = repository.simulate_movement()
            st.success(f"{moved} nova(s) leitura(s) registrada(s).")
            st.rerun()

    try:
        records = repository.find_within_radius(longitude, latitude, radius_km)
    except (PyMongoError, ValueError) as error:
        st.error(f"Falha na consulta geoespacial: {error}")
        return

    st.metric("Veículos encontrados", len(records))
    st_folium(build_map(longitude, latitude, radius_km, records), use_container_width=True, height=560)
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
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhum veículo foi localizado dentro do raio selecionado.")


if __name__ == "__main__":
    main()