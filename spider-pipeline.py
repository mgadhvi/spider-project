import requests
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from shapely.geometry import Point
import time


def fetch_inaturalist_data():
    base_url = "https://api.inaturalist.org/v1/observations"
    params = {
        "geo": "true",
        "verifiable": "true",
        "place_id": 6857,
        "taxon_name": "Spider",
        "created_d1": "2025-01-01",
        "geoprivacy": "open",
        "taxon_geoprivacy": "open",
        "obscuration": "none",
        "quality_grade": "research",
        "reviewed": "true",
        "per_page": 200,
        "order": "desc",
        "order_by": "created_at"
    }

    print("Fetching total results...")
    response = requests.get(base_url, params={**params, "page": 1})
    data = response.json()
    total_results = data['total_results']
    pages = (total_results // params["per_page"]) + 1
    print(f"Total results: {total_results}, pages: {pages}")

    all_observations = []
    for page in range(1, pages + 1):
        print(f"Fetching page {page} of {pages}")
        resp = requests.get(base_url, params={**params, "page": page})
        if resp.status_code != 200:
            print(f"Error fetching page {page}")
            continue
        results = resp.json()['results']
        all_observations.extend(results)
        time.sleep(1)  # Respect API rate limits

    return all_observations


def process_observations(observations):
    records = []
    for i, obs in enumerate(observations, start=1):
        if not obs.get("geojson"):
            continue
        lat = obs["geojson"]["coordinates"][1]
        lon = obs["geojson"]["coordinates"][0]
        species = obs["taxon"]["name"] if obs.get("taxon") else None
        species_guess = obs.get("species_guess")
        observed_on = obs.get("observed_on")
        records.append({
            "fid": i,
            "Species": species,
            "species_guess": species_guess,
            "Observed on": observed_on,
            "lat": lat,
            "lon": lon
        })

    df = pd.DataFrame(records)
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
    return gdf


def fetch_trust_boundaries():
    trust_url = (
        "https://services-eu1.arcgis.com/Y9jgVEvgymHqAYPW/arcgis/rest/services/"
        "Wildlife_Trust_Regional_Boundaries_-_Open_Data/FeatureServer/0/query"
        "?outFields=*&where=1%3D1&f=geojson"
    )
    return gpd.read_file(trust_url)


def spatial_join_sightings_with_trusts(sightings_gdf, trust_gdf):
    sightings_gdf = sightings_gdf.to_crs(trust_gdf.crs)
    joined = gpd.sjoin(sightings_gdf, trust_gdf, how="left", predicate="within")
    joined = joined.rename(columns={"Trust": "Trust"})
    return joined


def export_to_csv(joined_gdf, filename="spider_sightings_with_trust.csv"):
    final_df = joined_gdf[["fid", "Species", "species_guess", "Observed on", "lat", "lon", "Trust"]]
    final_df.to_csv(filename, index=False)
    print(f"Saved final CSV as {filename}")


def generate_folium_map(sightings_gdf, trust_gdf, map_filename="spider_map.html"):
    # Create the map centered on the UK
    m = folium.Map(location=[54, -2], zoom_start=6, tiles="cartodbpositron")

    # Add Trust boundaries to the map
    folium.GeoJson(
        trust_gdf, 
        name="Wildlife Trusts", 
        tooltip=folium.GeoJsonTooltip(fields=["Trust"])  # Using the correct 'Trust' field for the tooltip
    ).add_to(m)

    # Marker Cluster for clustered points (spider sightings)
    marker_cluster = MarkerCluster(name="Spider Sightings (Clustered)").add_to(m)

    # Add individual markers (for each spider sighting)
    for _, row in sightings_gdf.iterrows():
        popup = folium.Popup(f"{row['species_guess']} ({row['Species']})<br>{row['Observed on']}", max_width=300)
        
        # Add the marker to the marker cluster
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=popup
        ).add_to(marker_cluster)

    # Add Layer Control for toggling between layers
    folium.LayerControl().add_to(m)

    # Save the map
    m.save(map_filename)
    print(f"Saved Folium map to {map_filename}")


def main():
    # Step 1: Fetch spider data and process it
    observations = fetch_inaturalist_data()
    sightings_gdf = process_observations(observations)

    # Step 2: Fetch Wildlife Trust boundaries
    trust_gdf = fetch_trust_boundaries()

    # Step 3: Perform spatial join of sightings with trust boundaries
    joined_gdf = spatial_join_sightings_with_trusts(sightings_gdf, trust_gdf)

    # Step 4: Export the final data to CSV
    export_to_csv(joined_gdf)

    # Step 5: Generate the Folium map directly from the GeoDataFrame
    generate_folium_map(joined_gdf, trust_gdf)


if __name__ == "__main__":
    main()
