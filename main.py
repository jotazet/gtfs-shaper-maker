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
def get_route(start_coords, end_coords):
    route_url = f"http://localhost:5000/route/v1/train/{start_coords};{end_coords}?overview=full&geometries=geojson"
    response = requests.get(route_url, timeout=5)
    if response.status_code == 200:
        data = response.json()
        if data.get("code") == "Ok" and "routes" in data:
            # Access the first route in the list
            if data["routes"]:
                return data["routes"][0]["geometry"]["coordinates"]
            else:
                print("No routes found in the response.")
    return None

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

                previous_end_coords = None
                for i, matching in enumerate(data["matchings"]):
                    # Handle gap at the beginning
                    if i == 0:
                        first_matching_start = f"{matching['geometry']['coordinates'][0][0]},{matching['geometry']['coordinates'][0][1]}"
                        if coords_list[0] != first_matching_start:
                            route_coords = get_route(coords_list[0], first_matching_start)
                            if route_coords is not None:
                                all_coordinates.extend(route_coords)

                    # If there is a gap, fill it using get_route
                    if previous_end_coords is not None:
                        start_coords = f"{matching['geometry']['coordinates'][0][0]},{matching['geometry']['coordinates'][0][1]}"
                        route_coords = get_route(previous_end_coords, start_coords)
                        if route_coords is not None:
                            all_coordinates.extend(route_coords)

                    # Add current matching coordinates
                    all_coordinates.extend(matching["geometry"]["coordinates"])

                    # Update previous_end_coords to the last point of the current matching
                    previous_end_coords = f"{matching['geometry']['coordinates'][-1][0]},{matching['geometry']['coordinates'][-1][1]}"

                # Handle gap at the end
                last_matching_end = previous_end_coords
                if last_matching_end and coords_list[-1] != last_matching_end:
                    route_coords = get_route(last_matching_end, coords_list[-1])
                    if route_coords is not None:
                        all_coordinates.extend(route_coords)

                # Filter coordinates to reduce the number of points
                filtered = [all_coordinates[0]] + all_coordinates[1:-1:3] + [all_coordinates[-1]]
                return trip_id, filtered
            else:
                print(f"Unexpected API response: {data}")
        else:
            # Attempt to fetch the route directly
            if len(coords_list) >= 2:
                start_coords = coords_list[0]
                end_coords = coords_list[-1]
                route_coords = get_route(start_coords, end_coords)
                if route_coords is not None:
                    # Filter coordinates to reduce the number of points
                    filtered = [route_coords[0]] + route_coords[1:-1:3] + [route_coords[-1]]
                    return trip_id, filtered

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

with ThreadPoolExecutor(max_workers=12) as executor:
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