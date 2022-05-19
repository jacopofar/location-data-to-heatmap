from dataclasses import dataclass
import json
from pathlib import Path
from sys import argv

INTERMEDIATE_POINTS = 3


@dataclass
class Point:
    lat: float
    lng: float
    accuracyMeters: int | None = None

    def __hash__(self) -> int:
        return hash(self.lat) ^ hash(self.lng) ^ hash(self.accuracyMeters)


@dataclass
class Activity:
    type: str
    points: list[Point]


def read_file(fname) -> dict[str, list[Activity]]:
    ret = {}
    with open(fname) as f:
        raw_data = json.load(f)
    for event in raw_data["timelineObjects"]:
        if "activitySegment" not in event:
            continue
        if "activityType" not in event["activitySegment"]:
            # old files usually
            print(f"Ignoring a segment without an activity type")
            continue
        activity_type = event["activitySegment"]["activityType"]
        if "simplifiedRawPath" in event["activitySegment"]:
            waypoints_raw = event["activitySegment"]["simplifiedRawPath"]["points"]
        elif "waypointPath" in event["activitySegment"]:
            waypoints_raw = event["activitySegment"]["waypointPath"]["waypoints"]
        else:
            print(f"No waypoints found for {activity_type}, skipping...")
            continue
        points: list[Point] = []
        for wr in waypoints_raw:
            if "latE7" in wr:
                points.append(
                    Point(
                        wr["latE7"] / 1e7,
                        wr["lngE7"] / 1e7,
                        accuracyMeters=wr.get("accuracyMeters"),
                    )
                )
            elif "latitudeE7" in wr:
                points.append(
                    Point(
                        wr["latitudeE7"] / 1e7,
                        wr["longitudeE7"] / 1e7,
                        accuracyMeters=wr.get("accuracyMeters"),
                    )
                )
            else:
                raise Exception(f"Unknown waypoint format: {wr}")
        print(f"Activity {activity_type} had {len(points)} waypoints")

        if activity_type not in ret:
            ret[activity_type] = []

        ret[activity_type].append(Activity(activity_type, points))
    return ret


def activity_grid(
    activities: dict[str, list[Activity]], rounding: int
) -> dict[str, list[Point]]:
    """Aggregates waypoints to the given rounding.

    Rounding is here the number of decimals after the decimal separator.
    So rounding = 3 means that the first 3 decimals are used
    """
    ret: dict[str, dict[Point, int]] = {}
    for activity_type, activities in activities.items():
        ret[activity_type] = {}
        for activity in activities:
            # assume only some activities actually let you explore the world
            if activity_type not in ("WALKING", "CYCLING", "RUNNING"):
                for point in activity.points:
                    rounded_point = Point(
                        round(point.lat * (10**rounding)) / (10**rounding),
                        round(point.lng * (10**rounding)) / (10**rounding),
                    )
                    if rounded_point not in ret[activity_type]:
                        ret[activity_type][rounded_point] = 1
                    ret[activity_type][rounded_point] += 1
            else:
                visited_points = set()
                for p1, p2 in zip(activity.points, activity.points[1:]):
                    # brutal interpolation
                    for s in range(INTERMEDIATE_POINTS):
                        lat_i = p1.lat + (p2.lat - p1.lat) * s / INTERMEDIATE_POINTS
                        lng_i = p1.lng + (p2.lng - p1.lng) * s / INTERMEDIATE_POINTS
                        rounded_point = Point(
                            round(lat_i * (10**rounding)) / (10**rounding),
                            round(lng_i * (10**rounding)) / (10**rounding),
                        )
                        visited_points.add(rounded_point)
                for rounded_point in visited_points:
                    if rounded_point not in ret[activity_type]:
                        ret[activity_type][rounded_point] = 1
                    ret[activity_type][rounded_point] += 1

    return ret


if __name__ == "__main__":
    if len(argv) == 1:
        print("Usage: python3 location_to_geojson.py /path/to/google/takeout/Semantic Location History")
        exit(1)
    PRECISION = 3
    total_grid = {"ALL": {}}
    for fname in Path(argv[1]).glob("**/*.json"):
        print(f"Processing {fname}")
        data = read_file(fname)
        grid = activity_grid(data, PRECISION)
        for activity_type, points in grid.items():
            if activity_type not in total_grid:
                total_grid[activity_type] = {}
            for point, count in points.items():
                if point not in total_grid[activity_type]:
                    total_grid[activity_type][point] = count
                total_grid[activity_type][point] += count

                if point not in total_grid["ALL"]:
                    total_grid["ALL"][point] = count
                total_grid["ALL"][point] += count

    for activity_type, point_count in total_grid.items():
        features = []
        for tile, count in point_count.items():
            coords = [
                [tile.lng, tile.lat],
                [tile.lng, tile.lat + 1 / 10**PRECISION],
                [tile.lng + 1 / 10**PRECISION, tile.lat + 1 / 10**PRECISION],
                [tile.lng + 1 / 10**PRECISION, tile.lat],
                [tile.lng, tile.lat],
                [tile.lng + 1 / 10**PRECISION, tile.lat + 1 / 10**PRECISION],
            ]
            feature = {
                "type": "Feature",
                "properties": {"type": activity_type, "count": count},
                "geometry": {"type": "LineString", "coordinates": coords},
            }
            features.append(feature)

        geojson = {"type": "FeatureCollection", "features": features}
        with open(f"history_{activity_type}.geojson", "w") as fw:
            json.dump(geojson, fw, indent=2)
