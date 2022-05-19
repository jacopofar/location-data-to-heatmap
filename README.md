# Location to heatmap

# Archived
This project is archived, Google Takeout now has a better format and there are better ways to generate this representation.

Have a look at `location_to_geojson.py` (no dependencies needed) to generate GeoJSON files from your activities that can be loaded in QGIS or [geojson.io](https://geojson.io/#map=2/20.0/0.0) and many other tools.

To generate raster representations like this I strongly recommend [Datashader](https://datashader.org/), it's powerful, easy to use and fast.

This repository is now kept only for reference.
## Old readme for reference

This tool creates static and animated heatmaps of a given zone based on the data from Google location service.

It can be useful to find parts of a city that you never visited and visualize your movement and habits.

![Heatmap of locations in Berlin](locations_in_berlin_all_time_weighted.png)

Click here to see the ![animated version](berlin.webm)


## Usage
You need to have the Google location service active for some time to collect the data. Use [Google Takeout](https://takeout.google.com/) to export the location history.

Then, choose a city or region you are interested in and produce a background map, for example taking a screenshot of Open Street Map.

Then, create a virtualenv, install the dependencies and run the script like this (example coordinates for Berlin, Germany):

    python3 -m venv .venv
    python3 -m pip install -r requirements.txt
    python3 process.py region_name 132700000 135500000 524300000 526000000 1500 /path/to/location/history/export.json /path/to/background/map/image.png

You can use `python3 process.py --help` to get a description, but in short the numbers you see are the decimal coordinates multiplied by 10^7, the zoom level (1000 = 1 pixel per 10 meters).

It will create a global heatmap and one for every 15 minutes span after midnight. These images are then merged in an animated GIF and a webm video using the amazing [MoviePy](http://zulko.github.io/moviepy/) library.

## License
MIT licensed, use as you wish.

Made with ❤️ with Python and open source libraries.
