import argparse
import gtfs_kit as gk
import pandas as pd
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# 1. Set arguments
parser = argparse.ArgumentParser(description='Process GTFS data.')
parser.add_argument('file_name', type=str, help='Path to the GTFS zip file')
args = parser.parse_args()

start = time.time()

file_name = args.file_name

# 2. Load GTFS data
feed = gk.read_feed(file_name, dist_units="km")

# 3. Filter routes for trains (route_type == 2)
train_routes = feed.routes[feed.routes['route_type'] == 2]

# 4. Get trips for these routes
train_route_ids = train_routes['route_id'].tolist()
train_trips = feed.trips[feed.trips['route_id'].isin(train_route_ids)]

# 5. Get stop_times for these trips
train_trip_ids = train_trips['trip_id'].tolist()
train_stop_times = feed.stop_times[feed.stop_times['trip_id'].isin(train_trip_ids)]

# 6. Prepare cache of stop coordinates
stop_coords = {
    row['stop_id']: (row['stop_lat'], row['stop_lon'])
    for _, row in feed.stops.iterrows()
}

# 7. Function to fetch route shape from OSRM
def fetch_shape(trip_id, stop_ids):
    coords_list = []

    for stop_id in stop_ids:
        lat, lon = stop_coords.get(stop_id, (None, None))
        if lat is None or lon is None:
            return None
        coords_list.append(f"{lon},{lat}")

    coords = ";".join(coords_list)
    
    url = f"http://localhost:5000/match/v1/train/{coords}?overview=full&geometries=geojson"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "Ok" and "matchings" in data:
                # Collect all geometries from matchings
                all_coordinates = []
                for matching in data["matchings"]:
                    all_coordinates.extend(matching["geometry"]["coordinates"])
                
                # Filter coordinates to reduce the number of points
                filtered = [all_coordinates[0]] + all_coordinates[1:-1:3] + [all_coordinates[-1]]
                return trip_id, filtered
            else:
                print(f"Unexpected API response: {data}")
    except requests.exceptions.RequestException as e:
        print(f"Request failed for trip_id {trip_id}: {e}")
    return None

# 8. Prepare list of tasks
tasks = []
for trip_id, group in train_stop_times.groupby('trip_id'):
    sorted_group = group.sort_values('stop_sequence')
    if len(sorted_group) < 3:
        continue

    # Select every station (can be adjusted to every second with ::2)
    selected_stops = sorted_group.iloc[::1]['stop_id'].tolist()
    tasks.append((trip_id, selected_stops))

# 9. Parallel route fetching
all_shapes = []
shape_id = 0

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(fetch_shape, *task) for task in tasks]
    for future in as_completed(futures):
        result = future.result()
        if result is None:
            continue
        trip_id, coords = result

        shape_id_str = f"sh_{shape_id}"
        lats = [lat for lon, lat in coords]
        lons = [lon for lon, lat in coords]
        sequences = list(range(len(coords)))

        new_shapes = pd.DataFrame({
            'shape_id': shape_id_str,
            'shape_pt_lat': lats,
            'shape_pt_lon': lons,
            'shape_pt_sequence': sequences,
            'shape_dist_traveled': None
        })
        all_shapes.append(new_shapes)
        feed.trips.loc[feed.trips['trip_id'] == trip_id, 'shape_id'] = shape_id_str
        shape_id += 1

# 10. Combine all shapes
feed.shapes = pd.concat(all_shapes, ignore_index=True)

# 11. Save updated GTFS file
output_path = Path(f"shaped-{file_name}")
feed.to_file(output_path)

print(f"Execution time: {time.time() - start:.2f} seconds")
