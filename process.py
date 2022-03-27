import json
from datetime import datetime
import argparse

import imageio
import numpy as np
from scipy import ndimage
from matplotlib import pyplot as plt
import matplotlib.image as img
from skimage.transform import resize
from moviepy.video.io.ImageSequenceClip import ImageSequenceClip


def iso8601_to_epoch(iso_date: str):
    return datetime.fromisoformat(iso_date[:19]).strftime('%s')

def get_locations(
    location_data, x0, x1, y0, y1, scaling_factor,
    minutes_since_last_midnight_filter=None,
        ):
    """Produce an heatmap matrix of the given bounding box and scaling.

    Coordinates are in E7 format (decimal degrees multiplied by 10^7,
    and rounded to be integers).

    Optionally a range of minutes after midnight can be given.

    Parameters
    ----------
    location_data : dict
        the 'location' key of from Google location data export
    x0 : int
        longitude min, in E7 format
    x1 : int
        longitude max, in E7 format
    y0 : int
        latitude min, in E7 format
    y1 : int
        latitude max, in E7 format
    scaling_factor : int
        scaling factor, the higher the bigger the matrix
        1000 means about 1 cell per 10 meters
        1 px = 10 meters = ~0.00009 lat/long degrees
    minutes_since_last_midnight_filter : Tuple[int, int], optional
        the number of minutes, if specified will consider only the points
        with a timestamp that is N minutes after UTC midnight, where N is
        between the two given values

    Returns
    -------
    Tuple[ndarray, int, int]
        The resulting heatmap, and the number of processed and skipped entries
    """

    height_in_pixels = int((y1 - y0) / scaling_factor)
    width_in_pixels = int((x1 - x0) / scaling_factor)
    map_size = (height_in_pixels, width_in_pixels)

    place_map = np.zeros(map_size)

    processed, skipped = 0, 0
    for index_location, loc in enumerate(location_data):
        processed += 1
        if minutes_since_last_midnight_filter is not None:
            dt = datetime.fromtimestamp(int(iso8601_to_epoch(loc['timestamp']))/1000)
            sample_minutes = dt.hour * 60 + dt.minute
            if (sample_minutes < minutes_since_last_midnight_filter[0] or
                    sample_minutes > minutes_since_last_midnight_filter[1]):
                skipped += 1
                continue
        x = round((int(loc['longitudeE7'] - x0)) / scaling_factor)
        y = round((int(loc['latitudeE7'] - y0)) / scaling_factor)
        if (x >= place_map.shape[1] or
                y >= place_map.shape[0] or x < 0 or y < 0):
            skipped += 1
        else:
            if index_location + 1 < len(location_data):
                place_map[y][x] += (
                    (int(iso8601_to_epoch(loc['timestamp'])) -
                        int(iso8601_to_epoch(location_data[index_location + 1]['timestamp'])))
                    / (1000 * 60))
            else:
                place_map[y][x] += 1
    print('dots processed:', processed, 'dots outside the rectangle:', skipped)
    return place_map, processed, skipped


def main(
    input_file: str,
    base_file: str,
    place_name: str,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
    scaling_factor: int,
        ):
    print('Reading location data JSON...')
    location_data = json.loads(open(input_file).read())['locations']
    print('Data imported. Processing...')

    bins = list(range(1, 100, 1))
    minutes_step = 15
    # weight of previous frames over new one. The inverse of the decay factor
    frame_persistence_factor = 4

    all_minutes_starts = list(range(0, 24*60, minutes_step))
    base_map = np.mean(img.imread(base_file), axis=-1)
    base_map = np.stack([base_map, base_map, base_map], axis=-1)
    moving_average_frame = None
    quintiles = None
    filenames = []
    fig = None
    for frame_idx, selected_minute in enumerate(
            [None] + all_minutes_starts):
        print(f'frame {frame_idx} of {len(all_minutes_starts)}')
        place_map, processed, skipped = get_locations(
            location_data,
            x0,
            x1,
            y0,
            y1,
            scaling_factor,
            minutes_since_last_midnight_filter=((
                selected_minute, selected_minute + minutes_step)
                if selected_minute is not None else None))

        place_map_draw = None

        if processed == skipped:
            print('no points for this map, generating an empty one')
            place_map_draw = place_map
        else:
            place_map_blurred = ndimage.filters.gaussian_filter(
                place_map, 1)
            flattened = place_map_blurred.flatten()
            if selected_minute is None:
                # the first iteration is over non-time filtered point
                # and is used to generate the bin once for all
                quintiles = np.percentile(
                    flattened[np.nonzero(flattened)], bins)
            place_map_draw = np.searchsorted(
                quintiles, place_map_blurred) / len(bins)

        if base_map.shape != place_map_draw.shape:
            base_map = resize(
                base_map, place_map_draw.shape, anti_aliasing=True)

        if moving_average_frame is None:
            moving_average_frame = place_map_draw
        else:
            moving_average_frame = (
                (moving_average_frame +
                    place_map_draw * frame_persistence_factor)
                / (1 + frame_persistence_factor))
        print('min/avg/max of original matrix:'
              f'{np.min(place_map_draw,axis=(0,1))}/'
              f'{np.average(place_map_draw,axis=(0,1))}/'
              f'{np.max(place_map_draw,axis=(0,1))}')
        my_dpi = 90
        if fig is None:
            fig = plt.figure(
                    figsize=(
                        place_map_draw.shape[1]/my_dpi,
                        place_map_draw.shape[0]/my_dpi),
                    dpi=my_dpi)
        if selected_minute is not None:
            plt.title(f'Location history for zone: {place_name} and'
                      f' hour {int(selected_minute / 60)}:'
                      f'{(selected_minute % 60):02}'
                      f' + {minutes_step} minutes (UTC)')
        else:
            plt.title(f'Location history for zone: {place_name}'
                      ' at any moment of the day')

        plt.xlabel('Longitude')
        plt.ylabel('Latitude')
        # extent is used to show the coordinates in the axis
        plt.imshow(
            base_map,
            extent=[v/10000000 for v in [x0, x1, y0, y1]],
            alpha=0.48)
        plt.imshow(
            moving_average_frame,
            cmap=plt.cm.Spectral,
            extent=[v/10000000 for v in [x0, x1, y0, y1]],
            origin='lower',
            alpha=0.5)
        if selected_minute is not None:
            # note the :04 to add the trailing 0s
            # so the lexicographic order is numeric as well
            # and the subsequent command line command follows it
            frame_file = (f'locations_in_{place_name}_time_'
                          f'{frame_idx:04}.png')
            plt.savefig(frame_file)
            filenames.append(frame_file)
        else:
            plt.savefig(f'locations_in_{place_name}'
                        '_all_time_weighted.png')
        if selected_minute is None:
            # for simplicity, everything is drawn on the same matrix
            # it has to be "cleared" to avoid a "flash" on the first frame
            moving_average_frame = None
            # then, also move the quintiles so that the expected
            # distribution of values in a frame in normalized
            # for the total time, otherwise, calculating the
            # quintiles over the whole day, every frame would be dark
            quintiles = quintiles * len(all_minutes_starts)
        # clear the figure, faster than deleting and recreating a new one
        plt.clf()
    print('generating the GIF...')
    with imageio.get_writer(
        f'{place_name}.gif',
        mode='I',
        duration=0.3,
        subrectangles=True,
            ) as writer:
        for filename in filenames:
            print(f'Appending frame {filename} to the GIF')
            image = imageio.imread(filename)
            # GIF is quite space hungry
            if image.shape[0] > 500:
                factor = image.shape[0] / 500
                image = resize(
                    image,
                    (round(image.shape[0] / factor),
                        round(image.shape[1] / factor),
                        image.shape[2]),
                    anti_aliasing=True)
            writer.append_data(image)

    print('generating the video...')
    isc = ImageSequenceClip(filenames, fps=4)
    isc.write_videofile(f'{place_name}.webm')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('place_name', help='Name for the title')
    parser.add_argument('x0', type=int, help='min longitude, in E7 format')
    parser.add_argument('x1', type=int, help='max longitude, in E7 format')
    parser.add_argument('y0', type=int, help='min latitude, in E7 format')
    parser.add_argument('y1', type=int, help='max latituden, in E7 format')
    parser.add_argument(
        'scaling_factor',
        type=int,
        help='''
        scaling factor between pixels and coordinates.
        1000 means about 1 cell per 10 meters
        1 px = 10 meters = ~0.00009 lat/long degrees
        ''')
    parser.add_argument('input_file', help='input Takeout JSON')
    parser.add_argument(
        'base_file',
        help='the map background for the given coordinates')

    args = parser.parse_args()
    main(
        args.input_file,
        args.base_file,
        args.place_name,
        args.x0,
        args.x1,
        args.y0,
        args.y1,
        args.scaling_factor,
        )
