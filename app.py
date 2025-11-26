import streamlit as st
import pandas as pd
import zipfile
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="GTFS Analyzer avec Carte Interactive", layout="wide")
st.title("GTFS Analyzer avec Carte Interactive")

uploaded_file = st.file_uploader("Upload GTFS ZIP", type="zip")

def _read_csv_from_zip(z, name):
    try:
        with z.open(name) as f:
            return pd.read_csv(f)
    except KeyError:
        return None

if uploaded_file:
    with zipfile.ZipFile(uploaded_file) as z:
        # Charger les fichiers GTFS nécessaires
        stops = _read_csv_from_zip(z, "stops.txt")
        routes = _read_csv_from_zip(z, "routes.txt")
        trips = _read_csv_from_zip(z, "trips.txt")
        stop_times = _read_csv_from_zip(z, "stop_times.txt")
        shapes = _read_csv_from_zip(z, "shapes.txt")

        required = {"stops.txt": stops, "routes.txt": routes, "trips.txt": trips, "stop_times.txt": stop_times}
        missing = [k for k, v in required.items() if v is None]
        if missing:
            st.error(f"Fichiers GTFS incomplets: {', '.join(missing)} manquant(s).")
            st.stop()

        # Harmoniser les types pour éviter les erreurs de merge
        for df in [stops, stop_times]:
            if "stop_id" in df.columns:
                df["stop_id"] = df["stop_id"].astype(str)
        if "trip_id" in stop_times.columns:
            stop_times["trip_id"] = stop_times["trip_id"].astype(str)
        if "trip_id" in trips.columns:
            trips["trip_id"] = trips["trip_id"].astype(str)
        if "route_id" in trips.columns:
            trips["route_id"] = trips["route_id"].astype(str)
        if "route_id" in routes.columns:
            routes["route_id"] = routes["route_id"].astype(str)

        # --- Barre latérale : filtres ---
        st.sidebar.header("Filtres")

        # Préparer un label lisible pour les routes
        def format_route_label(row):
            short = str(row.get("route_short_name", "")).strip()
            long = str(row.get("route_long_name", "")).strip()
            rid = row["route_id"]
            if short and long:
                return f"{short} — {long} [{rid}]"
            elif short:
                return f"{short} [{rid}]"
            elif long:
                return f"{long} [{rid}]"
            else:
                return str(rid)

        route_options_df = routes.copy()
        route_options_df["label"] = route_options_df.apply(format_route_label, axis=1)
        route_label = st.sidebar.selectbox("Choisir une route", route_options_df["label"].tolist())
        selected_route = route_options_df.loc[route_options_df["label"] == route_label, "route_id"].iloc[0]

        trips_for_route = trips[trips["route_id"] == selected_route].copy()

        # Direction
        use_direction_id = ("direction_id" in trips_for_route.columns) and (trips_for_route["direction_id"].dropna().nunique() > 0)
        if use_direction_id:
            dir_values = sorted(trips_for_route["direction_id"].dropna().astype(int).unique().tolist())
            dir_labels = [f"direction_id = {d}" for d in dir_values]
            selected_dir_label = st.sidebar.radio("Choisir une direction", dir_labels)
            selected_direction_value = dir_values[dir_labels.index(selected_dir_label)]
            trips_lv2 = trips_for_route[trips_for_route["direction_id"] == selected_direction_value].copy()
        else:
            if "trip_headsign" in trips_for_route.columns and trips_for_route["trip_headsign"].dropna().nunique() > 0:
                headsign_values = sorted(trips_for_route["trip_headsign"].dropna().unique().tolist())
                selected_headsign = st.sidebar.selectbox("Choisir une direction (par headsign)", headsign_values)
                trips_lv2 = trips_for_route[trips_for_route["trip_headsign"] == selected_headsign].copy()
            else:
                st.sidebar.info("Aucune 'direction_id' ni 'trip_headsign' utilisable; tous les voyages de la route seront listés.")
                trips_lv2 = trips_for_route.copy()

        trips_lv2 = trips_lv2.copy()
        trips_lv2["label"] = trips_lv2.apply(lambda row: f"{row['trip_id']} — {row.get('trip_headsign','')} (service {row.get('service_id','')})", axis=1)
        if trips_lv2.empty:
            st.warning("Aucun voyage disponible pour la route/direction sélectionnée.")
            st.stop()

        trip_label = st.sidebar.selectbox("Choisir un voyage", trips_lv2["label"].tolist())
        selected_trip_id = trips_lv2.loc[trips_lv2["label"] == trip_label, "trip_id"].iloc[0]

        # Arrêts du voyage
        st.subheader("Arrêts pour le voyage sélectionné")
        stops_for_trip = stop_times[stop_times["trip_id"] == selected_trip_id].copy()
        if stops_for_trip.empty:
            st.warning("Aucun arrêt trouvé pour ce voyage.")
            st.stop()

        stops_for_trip["stop_id"] = stops_for_trip["stop_id"].astype(str)
        stops["stop_id"] = stops["stop_id"].astype(str)
        stops_joined = stops_for_trip.merge(stops, on="stop_id", how="left")
        if "stop_sequence" in stops_joined.columns:
            stops_joined = stops_joined.sort_values("stop_sequence")
        else:
            stops_joined = stops_joined.sort_values(["arrival_time", "departure_time"])

        display_cols = ["stop_sequence", "stop_id", "stop_name", "arrival_time", "stop_lat", "stop_lon"]
        display_cols = [c for c in display_cols if c in stops_joined.columns]
        st.dataframe(stops_joined[display_cols], use_container_width=True)

        first_stop = stops_joined.iloc[0]
        last_stop = stops_joined.iloc[-1]
        st.info(f"**Arrêt de départ**: {first_stop.get('stop_name','')} (ID: {first_stop.get('stop_id','')}, arrivée: {first_stop.get('arrival_time','')})

"
                f"**Arrêt de fin**: {last_stop.get('stop_name','')} (ID: {last_stop.get('stop_id','')}, arrivée: {last_stop.get('arrival_time','')})")

        csv = stops_joined[display_cols].to_csv(index=False).encode('utf-8')
        st.download_button("Exporter les arrêts (CSV)", csv, file_name=f"stops_{selected_trip_id}.csv", mime="text/csv")

        # Carte Folium avec fallback si NaN
        st.subheader("Carte interactive")
        lat_mean = stops_joined["stop_lat"].dropna().mean() if "stop_lat" in stops_joined.columns else None
        lon_mean = stops_joined["stop_lon"].dropna().mean() if "stop_lon" in stops_joined.columns else None
        if pd.isna(lat_mean) or pd.isna(lon_mean):
            st.warning("Coordonnées manquantes pour centrer la carte. Utilisation d'un fallback.")
            lat_mean, lon_mean = 45.5, -73.6

        m = folium.Map(location=[lat_mean, lon_mean], zoom_start=12)
        for _, row in stops_joined.iterrows():
            if pd.notnull(row.get("stop_lat")) and pd.notnull(row.get("stop_lon")):
                popup = f"<b>{row.get('stop_name','')}</b><br>ID: {row.get('stop_id','')}<br>Arrivée: {row.get('arrival_time','')}"
                folium.CircleMarker(location=[row["stop_lat"], row["stop_lon"]], radius=5, color="darkblue", fill=True, fill_opacity=0.9, popup=popup).add_to(m)

        if shapes is not None and "shape_id" in trips_lv2.columns:
            trip_row = trips_lv2[trips_lv2["trip_id"] == selected_trip_id].iloc[0]
            shape_id = trip_row.get("shape_id")
            if pd.notnull(shape_id):
                shp = shapes[shapes["shape_id"] == shape_id].copy()
                if "shape_pt_sequence" in shp.columns:
                    shp = shp.sort_values("shape_pt_sequence")
                coords = shp[["shape_pt_lat", "shape_pt_lon"]].dropna().values.tolist()
                if coords:
                    folium.PolyLine(coords, color="blue", weight=3, opacity=0.8, tooltip=f"shape_id: {shape_id}").add_to(m)

        st_folium(m, width=1000, height=600)

        anomalies = []
        missing_routes = set(trips["route_id"]) - set(routes["route_id"])
        if missing_routes:
            anomalies.append(f"Routes manquantes dans routes.txt: {missing_routes}")
        if anomalies:
            st.subheader("Anomalies détectées")
            st.write(anomalies)
