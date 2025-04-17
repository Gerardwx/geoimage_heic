#!/usr/bin/env python3

import os
import argparse
import sys
import re
from pathlib import Path

import exifread
from pillow_heif import HeifImagePlugin  # required to recognize HEIC
from PIL import Image, ImageDraw, ImageFont
import importlib.resources

# For plotting
import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import Point
import contextily as ctx
import math

# Path to your font resource
_FONT_PATH = Path(str(importlib.resources.files(__package__) / 'fonts' / 'Arimo-VariableFont_wght.ttf'))


def heic_to_jpeg(input_path, output_path, lat, lon):
    """Convert HEIC to JPEG with GPS footer text."""
    with Image.open(input_path) as img:
        img = img.convert("RGB")

        # Prepare footer text
        lat_f = float(lat)
        lon_f = float(lon)
        lat_hem = "N" if lat_f >= 0 else "S"
        lon_hem = "E" if lon_f >= 0 else "W"
        formatted_lat = f"{abs(lat_f):.5f}° {lat_hem}"
        formatted_lon = f"{abs(lon_f):.5f}° {lon_hem}"
        footer_text = f"Latitude: {formatted_lat}, Longitude: {formatted_lon}"

        # Font setup
        font_size = int(min(img.size) * 0.03)
        font = ImageFont.truetype(_FONT_PATH.as_posix(), font_size)

        # Measure text
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), footer_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # Create new image with footer space
        footer_h = text_h + 20
        new_img = Image.new("RGB", (img.width, img.height + footer_h), "white")
        new_img.paste(img, (0, 0))

        # Draw footer
        draw = ImageDraw.Draw(new_img)
        pos = ((new_img.width - text_w) // 2, img.height + 10)
        draw.text(pos, footer_text, font=font, fill="black")

        new_img.save(output_path, "JPEG")
        print(f"Saved image to {output_path}")

import piexif

def get_exif_data(file_path):
    """Extract GPSLatitude and GPSLongitude from HEIC file using pillow-heif + piexif."""
    try:
        with Image.open(file_path) as img:
            exif_bytes = img.info.get("exif")
            if not exif_bytes:
                return None, None
            exif_dict = piexif.load(exif_bytes)

            gps = exif_dict.get("GPS", {})
            lat = gps.get(piexif.GPSIFD.GPSLatitude)
            lon = gps.get(piexif.GPSIFD.GPSLongitude)
            lat_ref = gps.get(piexif.GPSIFD.GPSLatitudeRef, b'N').decode()
            lon_ref = gps.get(piexif.GPSIFD.GPSLongitudeRef, b'E').decode()

            def to_deg(values, ref):
                d, m, s = [v[0] / v[1] for v in values]
                sign = 1 if ref in ('N', 'E') else -1
                return sign * (d + m / 60 + s / 3600)

            if lat and lon:
                return to_deg(lat, lat_ref), to_deg(lon, lon_ref)
            return None, None
    except Exception as e:
        print(f"Error reading EXIF from {file_path}: {e}", file=sys.stderr)
        return None, None



def natural_key(s):
    """Key for natural sorting of filenames with numbers."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def plot_locations(points, output_dir):
    """
    Plot points on a satellite basemap with 40% margin and non-overlapping labels.
    """
    coords = [(float(lon), float(lat)) for lat, lon, _ in points]
    names = [name for _, _, name in points]
    prefix = os.path.commonprefix(names)
    labels = [n[len(prefix):] if n.startswith(prefix) else n for n in names]

    gdf = gpd.GeoDataFrame({'label': labels}, geometry=[Point(xy) for xy in coords], crs='EPSG:4326')
    gdf_web = gdf.to_crs(epsg=3857)

    minx, miny, maxx, maxy = gdf_web.total_bounds
    dx, dy = (maxx - minx) * 0.4, (maxy - miny) * 0.4
    bounds = (minx - dx, miny - dy, maxx + dx, maxy + dy)

    fig, ax = plt.subplots(figsize=(8, 8))
    gdf_web.plot(ax=ax, color='red', marker='o', markersize=50, zorder=2)

    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])

    ctx.add_basemap(ax, source=ctx.providers.Esri.WorldImagery, crs=gdf_web.crs, zoom=14, zorder=1)

    offset_mag = min((maxx - minx), (maxy - miny)) * 0.03
    n = len(gdf_web)

    for i, (pt, label) in enumerate(zip(gdf_web.geometry, gdf_web['label'])):
        angle = 2 * math.pi * i / n
        dx_off = math.cos(angle) * offset_mag
        dy_off = math.sin(angle) * offset_mag
        ax.text(pt.x + dx_off, pt.y + dy_off, label,
                fontsize=8, ha='center', va='center',
                bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='none', alpha=0.7),
                zorder=3)

    ax.axis('off')
    map_path = os.path.join(output_dir, 'map.png')
    fig.savefig(map_path, bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    print(f"Map saved to {map_path}")


def convert_heic_images(input_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    manifest_path = os.path.join(output_dir, 'manifest.html')
    points = []
    # Gather and sort filenames
    file_names = [f for f in os.listdir(input_dir) if f.lower().endswith('.heic')]
    file_names.sort(key=natural_key)
    with open(manifest_path, 'w') as manifest:
        manifest.write('<!DOCTYPE html>\n<html lang="en">\n<head>\n')
        manifest.write('  <meta charset="UTF-8">\n')
        manifest.write('  <title>Photo locations</title>\n')
        manifest.write('</head>\n<body>\n')
        manifest.write('  <h1>Photo locations</h1>\n')
        manifest.write('  <ul>\n')
        for file_name in file_names:
            in_path = os.path.join(input_dir, file_name)
            out_name = os.path.splitext(file_name)[0] + '.jpg'
            out_path = os.path.join(output_dir, out_name)
            lat, lon = get_exif_data(in_path)
            if lat is None or lon is None:
                print(f"{file_name} missing GPS data", file=sys.stderr)
                continue
            heic_to_jpeg(in_path, out_path, lat, lon)
            points.append((lat, lon, out_name))
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            manifest.write(f'    <li><a href="{maps_url}">{out_name}</a></li>\n')
        manifest.write('  </ul>\n')
        manifest.write('</body>\n</html>\n')
    print(f"Manifest saved to {manifest_path}")
    if points:
        plot_locations(points, output_dir)


def main():
    if not _FONT_PATH.is_file():
        raise FileNotFoundError(f"Font not found at {_FONT_PATH}")
    parser = argparse.ArgumentParser(
        description="Convert HEIC to JPEG, generate HTML manifest, plot locations"
    )
    parser.add_argument('input_dir', help='Directory of HEIC files')
    parser.add_argument('output_dir', help='Directory for outputs')
    args = parser.parse_args()
    convert_heic_images(args.input_dir, args.output_dir)

if __name__ == '__main__':
    main()

