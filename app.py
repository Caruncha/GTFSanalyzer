
import streamlit as st
import pandas as pd
import zipfile
import folium
from streamlit_folium import st_folium

st.title("GTFS Analyzer avec Carte Interactive")

uploaded_file = st.file_uploader("Upload GTFS ZIP", type="zip")

if uploaded_file:
    with zipfile.ZipFile(uploaded_file) as z:
        files = z.namelist()
        gtfs_data = {}
        for f in files:
            if f.endswith(".txt"):
                with z.open(f) as file:
                    gtfs_data[f] = pd.read_csv(file)

    # Vérifier les fichiers nécessaires
    stops = gtfs_data.get("stops.txt")
    routes = gtfs_data.get("routes.txt")
    trips = gtfs_data.get("trips.txt")
    stop_times = gtfs_data.get("stop_times.txt")
    shapes = gtfs_data.get("shapes.txt")

    if routes is None or trips is None or stops is None or stop_times is None:
        st.error("Fichiers GTFS incomplets. Assurez-vous que stops.txt, routes.txt, trips.txt et stop_times.txt sont présents.")
    else:
        # Sélecteurs dynamiques
        st.sidebar.header("Filtres")
        selected_route = st.sidebar.selectbox("Choisir une route", routes["route_id"].unique())
        trips_filtered = trips[trips["route_id"] == selected_route]
        selected_trip = st.sidebar.selectbox("Choisir un trip", trips_filtered["trip_id"].unique())

        # Stops pour ce trip
        stops_for_trip = stop_times[stop_times["trip_id"] == selected_trip]
        stops_filtered = stops[stops["stop_id"].isin(stops_for_trip["stop_id"])]

        # Carte Folium
        st.subheader("Carte interactive")
        m = folium.Map(location=[stops_filtered["stop_lat"].mean(), stops_filtered["stop_lon"].mean()], zoom_start=12)

        # Ajouter les arrêts
        for _, row in stops_filtered.iterrows():
            folium.Marker([row["stop_lat"], row["stop_lon"]], popup=row["stop_name"]).add_to(m)

        # Ajouter la polyline si shapes.txt existe
        if shapes is not None:
            shape_id = trips_filtered[trips_filtered["trip_id"] == selected_trip]["shape_id"].values[0]
            shape_points = shapes[shapes["shape_id"] == shape_id].sort_values("shape_pt_sequence")
            folium.PolyLine(shape_points[["shape_pt_lat", "shape_pt_lon"]].values, color="blue", weight=3).add_to(m)

        st_folium(m, width=800, height=600)

        # Tableau filtré
        st.subheader("Arrêts pour le trip sélectionné")
        st.dataframe(stops_filtered)

        # Détection d'anomalies simples
        anomalies = []
        missing_routes = set(trips["route_id"]) - set(routes["route_id"])
        if missing_routes:
            anomalies.append(f"Routes manquantes: {missing_routes}")

        st.subheader("Anomalies détectées")
        st.write(anomalies if anomalies else "Aucune anomalie détectée.")
