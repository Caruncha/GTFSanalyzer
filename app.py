import streamlit as st
import pandas as pd
import zipfile
import io
import plotly.express as px

# Configuration de la page
st.set_page_config(
    page_title="Analyseur GTFS Pro",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- FONCTIONS UTILITAIRES ---

@st.cache_data(show_spinner=False)
def load_gtfs_from_zip(uploaded_file):
    """Charge les fichiers GTFS d'un ZIP en mémoire dans un dictionnaire de DataFrames."""
    gtfs_data = {}
    required_files = ['agency.txt', 'stops.txt', 'routes.txt', 'trips.txt', 'stop_times.txt', 'calendar.txt']
    
    try:
        with zipfile.ZipFile(uploaded_file) as z:
            # Lister tous les fichiers dans le zip
            all_files = z.namelist()
            
            # Filtrer pour ne garder que les fichiers .txt pertinents
            for filename in all_files:
                if filename.endswith('.txt'):
                    file_key = filename.replace('.txt', '')
                    try:
                        # Lecture du fichier CSV
                        with z.open(filename) as f:
                            df = pd.read_csv(f, dtype=str) # Lire tout en string pour éviter les erreurs de type au début
                            gtfs_data[file_key] = df
                    except Exception as e:
                        st.error(f"Erreur lors de la lecture de {filename}: {e}")
            
            return gtfs_data, None
    except zipfile.BadZipFile:
        return None, "Le fichier fourni n'est pas un fichier ZIP valide."

def convert_types(df, table_name):
    """Convertit les colonnes numériques pour l'analyse et la visualisation."""
    df_copy = df.copy()
    if table_name == 'stops':
        if 'stop_lat' in df_copy.columns: df_copy['stop_lat'] = pd.to_numeric(df_copy['stop_lat'], errors='coerce')
        if 'stop_lon' in df_copy.columns: df_copy['stop_lon'] = pd.to_numeric(df_copy['stop_lon'], errors='coerce')
    return df_copy

def run_validation(data):
    """Exécute une série de vérifications d'intégrité sur les données GTFS."""
    anomalies = []
    
    # 1. Fichiers manquants (Validation basique)
    expected_files = ['agency', 'stops', 'routes', 'trips', 'stop_times', 'calendar']
    for f in expected_files:
        if f not in data:
            anomalies.append({"Type": "Critique", "Fichier": f, "Message": "Fichier manquant (obligatoire ou fortement recommandé)."})

    # Si les fichiers de base sont là, on fait des vérifications croisées
    if 'routes' in data and 'agency' in data and 'agency_id' in data['routes'].columns:
        # Vérifier que les routes référencent une agence valide
        invalid_agencies = data['routes'][~data['routes']['agency_id'].isin(data['agency']['agency_id'])]
        if not invalid_agencies.empty:
            anomalies.append({"Type": "Erreur", "Fichier": "routes", "Message": f"{len(invalid_agencies)} routes référencent un agency_id inconnu."})

    if 'trips' in data and 'routes' in data:
        # Vérifier que les trips référencent une route valide
        invalid_trips = data['trips'][~data['trips']['route_id'].isin(data['routes']['route_id'])]
        if not invalid_trips.empty:
            anomalies.append({"Type": "Erreur", "Fichier": "trips", "Message": f"{len(invalid_trips)} voyages (trips) référencent un route_id inconnu."})

    if 'stop_times' in data and 'trips' in data:
        # Vérifier que les stop_times référencent un trip valide
        # Attention: stop_times peut être très gros, on vérifie sur un échantillon ou on optimise
        unique_trip_ids_st = data['stop_times']['trip_id'].unique()
        unique_trip_ids_t = set(data['trips']['trip_id'].unique())
        invalid_st_trips = [t for t in unique_trip_ids_st if t not in unique_trip_ids_t]
        
        if invalid_st_trips:
             anomalies.append({"Type": "Erreur", "Fichier": "stop_times", "Message": f"{len(invalid_st_trips)} trip_ids dans stop_times n'existent pas dans trips."})

    if 'stop_times' in data and 'stops' in data:
        # Vérifier que les stop_times référencent un stop valide
        unique_stop_ids_st = data['stop_times']['stop_id'].unique()
        unique_stop_ids_s = set(data['stops']['stop_id'].unique())
        invalid_st_stops = [s for s in unique_stop_ids_st if s not in unique_stop_ids_s]
        
        if invalid_st_stops:
            anomalies.append({"Type": "Erreur", "Fichier": "stop_times", "Message": f"{len(invalid_st_stops)} stop_ids dans stop_times n'existent pas dans stops."})

    # Validation des doublons d'ID primaires
    primary_keys = {
        'stops': 'stop_id',
        'routes': 'route_id',
        'trips': 'trip_id',
        'agency': 'agency_id'
    }
    
    for table, pk in primary_keys.items():
        if table in data and pk in data[table].columns:
            if data[table][pk].duplicated().any():
                dup_count = data[table][pk].duplicated().sum()
                anomalies.append({"Type": "Avertissement", "Fichier": table, "Message": f"{dup_count} IDs dupliqués trouvés (colonne {pk})."})

    return pd.DataFrame(anomalies)

# --- INTERFACE UTILISATEUR ---

st.title("🚇 Analyseur & Validateur GTFS")
st.markdown("""
Cette application permet d'auditer un fichier GTFS, d'explorer ses données dynamiquement et de détecter les anomalies de structure.
""")

# Sidebar pour l'upload
with st.sidebar:
    st.header("Chargement")
    uploaded_file = st.file_uploader("Choisissez un fichier GTFS (.zip)", type="zip")
    st.info("Le traitement des gros fichiers peut prendre quelques secondes.")

if uploaded_file is not None:
    with st.spinner('Lecture et analyse du fichier GTFS...'):
        gtfs_data, error = load_gtfs_from_zip(uploaded_file)

    if error:
        st.error(error)
    elif gtfs_data:
        # Onglets principaux
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Vue d'ensemble", "🔍 Explorateur de Données", "⚠️ Rapport d'Anomalies", "🗺️ Carte"])

        # --- TAB 1: VUE D'ENSEMBLE ---
        with tab1:
            st.subheader("Statistiques Rapides")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                count = len(gtfs_data['routes']) if 'routes' in gtfs_data else 0
                st.metric("Lignes (Routes)", count)
            with col2:
                count = len(gtfs_data['stops']) if 'stops' in gtfs_data else 0
                st.metric("Arrêts (Stops)", count)
            with col3:
                count = len(gtfs_data['trips']) if 'trips' in gtfs_data else 0
                st.metric("Voyages (Trips)", count)
            with col4:
                count = len(gtfs_data['agency']) if 'agency' in gtfs_data else 0
                st.metric("Agences", count)

            st.markdown("### Fichiers détectés dans le ZIP")
            
            file_info = []
            for name, df in gtfs_data.items():
                file_info.append({
                    "Fichier": f"{name}.txt",
                    "Lignes": df.shape[0],
                    "Colonnes": df.shape[1],
                    "Colonnes détectées": ", ".join(list(df.columns)[:5]) + "..."
                })
            st.dataframe(pd.DataFrame(file_info), use_container_width=True)

        # --- TAB 2: EXPLORATEUR ---
        with tab2:
            st.subheader("Explorateur Interactif")
            
            file_options = list(gtfs_data.keys())
            selected_file = st.selectbox("Choisir le fichier à inspecter :", file_options, index=file_options.index('routes') if 'routes' in file_options else 0)
            
            if selected_file:
                df_view = gtfs_data[selected_file]
                
                # Filtres dynamiques
                st.markdown(f"**Données : {selected_file}.txt** ({len(df_view)} enregistrements)")
                
                # Recherche globale simple
                search_term = st.text_input(f"Filtrer {selected_file} (recherche textuelle globale)", "")
                
                if search_term:
                    # Filtre simple sur toutes les colonnes string
                    mask = df_view.apply(lambda x: x.astype(str).str.contains(search_term, case=False, na=False)).any(axis=1)
                    df_display = df_view[mask]
                else:
                    df_display = df_view

                st.dataframe(df_display, use_container_width=True, height=500)
                
                csv = df_display.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Télécharger ces données (CSV)",
                    data=csv,
                    file_name=f"{selected_file}_filtered.csv",
                    mime='text/csv',
                )

        # --- TAB 3: ANOMALIES ---
        with tab3:
            st.subheader("Validation et Intégrité")
            
            if st.button("Lancer l'analyse complète"):
                with st.spinner("Analyse des relations entre les fichiers..."):
                    anomalies_df = run_validation(gtfs_data)
                
                if anomalies_df.empty:
                    st.success("✅ Aucune anomalie majeure détectée dans la structure relationnelle standard.")
                else:
                    st.warning(f"⚠️ {len(anomalies_df)} anomalies potentielles détectées.")
                    
                    # Colorisation du tableau
                    def color_severity(val):
                        color = 'red' if val == 'Critique' else 'orange' if val == 'Erreur' else '#CCCC00'
                        return f'color: {color}; font-weight: bold'

                    st.dataframe(
                        anomalies_df.style.map(color_severity, subset=['Type']),
                        use_container_width=True
                    )
                    
                    with st.expander("Comprendre les erreurs"):
                        st.markdown("""
                        - **Critique** : Fichier manquant empêchant le fonctionnement du GTFS.
                        - **Erreur** : Rupture d'intégrité référentielle (ex: un voyage fait référence à une ligne qui n'existe pas). Cela fera planter la plupart des applications.
                        - **Avertissement** : Données potentiellement sales (doublons) mais souvent lisibles.
                        """)
            else:
                st.info("Cliquez sur le bouton pour lancer la vérification des clés étrangères et des données manquantes.")

        # --- TAB 4: CARTE ---
        with tab4:
            st.subheader("Visualisation Géographique")
            
            if 'stops' in gtfs_data:
                stops_df = gtfs_data['stops'].copy()
                
                # Conversion sécurisée
                if 'stop_lat' in stops_df.columns and 'stop_lon' in stops_df.columns:
                    stops_df['stop_lat'] = pd.to_numeric(stops_df['stop_lat'], errors='coerce')
                    stops_df['stop_lon'] = pd.to_numeric(stops_df['stop_lon'], errors='coerce')
                    
                    # Retirer les NaN
                    stops_df = stops_df.dropna(subset=['stop_lat', 'stop_lon'])
                    
                    if not stops_df.empty:
                        # Limiter le nombre de points pour la performance si nécessaire
                        if len(stops_df) > 5000:
                            st.warning(f"Affichage de 5000 arrêts sur {len(stops_df)} pour la performance.")
                            stops_viz = stops_df.sample(5000)
                        else:
                            stops_viz = stops_df

                        # Carte Plotly
                        fig = px.scatter_mapbox(
                            stops_viz, 
                            lat="stop_lat", 
                            lon="stop_lon", 
                            hover_name="stop_name" if "stop_name" in stops_viz.columns else "stop_id",
                            hover_data=["stop_id"],
                            zoom=10,
                            height=600
                        )
                        fig.update_layout(mapbox_style="open-street-map")
                        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.error("Les colonnes stop_lat/stop_lon ne contiennent pas de données numériques valides.")
                else:
                    st.error("Colonnes stop_lat ou stop_lon manquantes dans stops.txt")
            else:
                st.info("Fichier stops.txt non trouvé, impossible d'afficher la carte.")

else:
    # État vide (Landing page)
    st.info("👋 Veuillez charger un fichier ZIP GTFS dans la barre latérale pour commencer.")
    
    # Génération d'un exemple de structure pour l'affichage
    st.markdown("### Structure attendue d'un GTFS")
    st.code("""
    mon_gtfs.zip
    ├── agency.txt      (Requis : Agence de transport)
    ├── stops.txt       (Requis : Arrêts géolocalisés)
    ├── routes.txt      (Requis : Lignes/Parcours)
    ├── trips.txt       (Requis : Voyages)
    ├── stop_times.txt  (Requis : Horaires aux arrêts)
    └── calendar.txt    (Requis/Optionnel : Jours de service)
    """, language="text")
