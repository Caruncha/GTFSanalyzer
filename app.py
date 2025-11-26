
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
        calendar = _read_csv_from_zip(z, 'calendar.txt')
        calendar_dates = _read_csv_from_zip(z, 'calendar_dates.txt')

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

        # --- Sélecteurs ---
        st.sidebar.header('Filtres')

        # Sélection de la date avec jour de la semaine
        all_dates = []
        if calendar is not None:
            for _, row in calendar.iterrows():
                all_dates.extend(pd.date_range(start=str(row['start_date']), end=str(row['end_date'])).strftime('%Y%m%d').tolist())
        if calendar_dates is not None:
            all_dates.extend(calendar_dates['date'].astype(str).tolist())
        all_dates = sorted(set(all_dates))

        if not all_dates:
            st.error("Impossible de déterminer les dates de service (calendar.txt manquant ou vide).")
            st.stop()

        date_options = [f"{pd.to_datetime(d).strftime('%Y-%m-%d')} ({pd.to_datetime(d).strftime('%A')})" for d in all_dates]
        selected_date_display = st.sidebar.selectbox('Choisir une date', date_options)
        selected_date_str = selected_date_display.split(' ')[0].replace('-', '')

        # Filtrer les services actifs pour cette date
        active_services = set()
        if calendar is not None:
            for _, row in calendar.iterrows():
                if row['start_date'] <= int(selected_date_str) <= row['end_date']:
                    weekday = pd.to_datetime(selected_date_str).day_name().lower()
                    if row[weekday] == 1:
                        active_services.add(row['service_id'])
        if calendar_dates is not None:
            exceptions = calendar_dates[calendar_dates['date'] == int(selected_date_str)]
            for _, row in exceptions.iterrows():
                if row['exception_type'] == 1:
                    active_services.add(row['service_id'])
                elif row['exception_type'] == 2 and row['service_id'] in active_services:
                    active_services.remove(row['service_id'])

        trips_filtered = trips[trips['service_id'].isin(active_services)]

        if trips_filtered.empty:
            st.warning("Aucun voyage actif pour cette date.")
            st.stop()

        selected_route = st.sidebar.selectbox('Choisir une route', trips_filtered['route_id'].unique())
        trips_filtered = trips_filtered[trips_filtered['route_id'] == selected_route]
        selected_trip = st.sidebar.selectbox('Choisir un trip', trips_filtered['trip_id'].unique())

        # Stops pour ce trip
        stops_for_trip = stop_times[stop_times['trip_id'] == selected_trip]
        stops_filtered = stops.merge(stops_for_trip, on='stop_id', how='inner').sort_values('stop_sequence')

        st.subheader('Carte interactive')

        # Déterminer le centre de la carte avec fallback
        lat_mean = stops_filtered['stop_lat'].dropna().mean()
        lon_mean = stops_filtered['stop_lon'].dropna().mean()
        if pd.isna(lat_mean) or pd.isna(lon_mean):
            st.warning("Coordonnées manquantes pour centrer la carte. Utilisation d'un fallback.")
            lat_mean, lon_mean = 45.5, -73.6

        m = folium.Map(location=[lat_mean, lon_mean], zoom_start=14)

        # Ajouter la polyline en premier (derrière les arrêts)
        if shapes is not None and 'shape_id' in trips_filtered.columns:
            shape_id = trips_filtered[trips_filtered['trip_id'] == selected_trip]['shape_id'].values[0]
            shape_points = shapes[shapes['shape_id'] == shape_id].sort_values('shape_pt_sequence')
            if not shape_points.empty:
                folium.PolyLine(shape_points[['shape_pt_lat', 'shape_pt_lon']].values, color='blue', weight=4).add_to(m)

        # Ajouter les arrêts avec design demandé et popup amélioré
        n = len(stops_filtered)
        for idx, row in stops_filtered.reset_index().iterrows():
            la, lo = row['stop_lat'], row['stop_lon']
            if idx == 0:
                color = "green"; fill = "green"; radius = 7
            elif idx == n - 1:
                color = "red"; fill = "red"; radius = 7
            else:
                color = "#666666"; fill = "#ffffff"; radius = 5
            popup_html = f"""
            <div style="font-size:14px;">
                <b>{row['stop_name']}</b><br>
                ID: {row['stop_id']}<br>
                Heure d'arrivée: {row.get('arrival_time','')}
            </div>
            """
            folium.CircleMarker(
                location=(la, lo),
                radius=radius,
                color=color,
                fill=True,
                fill_color=fill,
                fill_opacity=0.95,
                weight=2,
                popup=popup_html
            ).add_to(m)

        # Ajouter une légende
        legend_html = """
        <div style="position: fixed; bottom: 50px; left: 50px; width: 180px; background-color: white; border:2px solid grey; z-index:9999; font-size:14px; padding:10px;">
            <b>Légende</b><br>
            <span style="color:green;">&#9679;</span> Départ<br>
            <span style="color:red;">&#9679;</span> Arrivée<br>
            <span style="color:#666666;">&#9679;</span> Arrêts intermédiaires
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width=900, height=600)

        st.subheader('Arrêts pour le trip sélectionné')
        st.dataframe(stops_filtered[['stop_id', 'stop_name', 'arrival_time']])

        # Export CSV
        csv = stops_filtered[['stop_id', 'stop_name', 'arrival_time']].to_csv(index=False).encode('utf-8')
        st.download_button("Exporter les arrêts (CSV)", csv, file_name=f"stops_{selected_trip}.csv", mime="text/csv")
