
import streamlit as st
import pandas as pd
import zipfile
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title='GTFS Analyzer avec Carte Interactive', layout='wide')
st.title('GTFS Analyzer avec Carte Interactive')

uploaded_file = st.file_uploader('Upload GTFS ZIP', type='zip')

def _read_csv_from_zip(z, name):
    try:
        with z.open(name) as f:
            return pd.read_csv(f)
    except KeyError:
        return None

if uploaded_file:
    with zipfile.ZipFile(uploaded_file) as z:
        stops = _read_csv_from_zip(z, 'stops.txt')
        routes = _read_csv_from_zip(z, 'routes.txt')
        trips = _read_csv_from_zip(z, 'trips.txt')
        stop_times = _read_csv_from_zip(z, 'stop_times.txt')
        shapes = _read_csv_from_zip(z, 'shapes.txt')

        if routes is None or trips is None or stops is None or stop_times is None:
            st.error('Fichiers GTFS incomplets. Assurez-vous que stops.txt, routes.txt, trips.txt et stop_times.txt sont présents.')
            st.stop()

        # Harmoniser les types
        for df in [stops, stop_times]:
            if 'stop_id' in df.columns:
                df['stop_id'] = df['stop_id'].astype(str)
        if 'trip_id' in stop_times.columns:
            stop_times['trip_id'] = stop_times['trip_id'].astype(str)
        if 'trip_id' in trips.columns:
            trips['trip_id'] = trips['trip_id'].astype(str)
        if 'route_id' in trips.columns:
            trips['route_id'] = trips['route_id'].astype(str)
        if 'route_id' in routes.columns:
            routes['route_id'] = routes['route_id'].astype(str)

        # Sélecteurs
        st.sidebar.header('Filtres')
        selected_route = st.sidebar.selectbox('Choisir une route', routes['route_id'].unique())
        trips_filtered = trips[trips['route_id'] == selected_route]
        selected_trip = st.sidebar.selectbox('Choisir un trip', trips_filtered['trip_id'].unique())

        # Stops pour ce trip
        stops_for_trip = stop_times[stop_times['trip_id'] == selected_trip]
        stops_filtered = stops.merge(stops_for_trip, on='stop_id', how='inner')

        st.subheader('Carte interactive')

        # Déterminer le centre de la carte avec fallback
        lat_mean = None
        lon_mean = None
        if shapes is not None and 'shape_id' in trips_filtered.columns:
            shape_id = trips_filtered[trips_filtered['trip_id'] == selected_trip]['shape_id'].values[0]
            shape_points = shapes[shapes['shape_id'] == shape_id].sort_values('shape_pt_sequence')
            if not shape_points.empty:
                lat_mean = shape_points['shape_pt_lat'].mean()
                lon_mean = shape_points['shape_pt_lon'].mean()
        if pd.isna(lat_mean) or pd.isna(lon_mean):
            lat_mean = stops_filtered['stop_lat'].dropna().mean()
            lon_mean = stops_filtered['stop_lon'].dropna().mean()
        if pd.isna(lat_mean) or pd.isna(lon_mean):
            st.warning("Coordonnées manquantes pour centrer la carte. Utilisation d'un fallback.")
            lat_mean, lon_mean = 45.5, -73.6

        m = folium.Map(location=[lat_mean, lon_mean], zoom_start=14)

        # Ajouter les arrêts avec design : cercles blancs, premier vert, dernier rouge, popup simple
        for i, row in stops_filtered.reset_index().iterrows():
            color = 'white'
            if i == 0:
                color = 'green'
            elif i == len(stops_filtered) - 1:
                color = 'red'
            folium.CircleMarker(
                location=[row['stop_lat'], row['stop_lon']],
                radius=7,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=1,
                popup=f"{row['stop_name']} (ID: {row['stop_id']})"
            ).add_to(m)

        # Ajouter la polyline si shapes.txt existe
        if shapes is not None:
            shape_id = trips_filtered[trips_filtered['trip_id'] == selected_trip]['shape_id'].values[0]
            shape_points = shapes[shapes['shape_id'] == shape_id].sort_values('shape_pt_sequence')
            if not shape_points.empty:
                folium.PolyLine(shape_points[['shape_pt_lat', 'shape_pt_lon']].values, color='blue', weight=4).add_to(m)

        # Ajouter une légende
        legend_html = """
        <div style="position: fixed; bottom: 50px; left: 50px; width: 180px; background-color: white; border:2px solid grey; z-index:9999; font-size:14px; padding:10px;">
            <b>Légende</b><br>
            <span style="color:green;">&#9679;</span> Départ<br>
            <span style="color:red;">&#9679;</span> Arrivée<br>
            <span style="color:black;">&#9679;</span> Arrêts intermédiaires
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width=900, height=600)

        st.subheader('Arrêts pour le trip sélectionné')
        st.dataframe(stops_filtered[['stop_id', 'stop_name', 'arrival_time']])

        # Export CSV
        csv = stops_filtered[['stop_id', 'stop_name', 'arrival_time']].to_csv(index=False).encode('utf-8')
        st.download_button("Exporter les arrêts (CSV)", csv, file_name=f"stops_{selected_trip}.csv", mime="text/csv")
