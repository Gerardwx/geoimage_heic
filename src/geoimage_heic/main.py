import os
import subprocess
import argparse
import sys
from pathlib import Path

from pillow_heif import HeifImagePlugin # required to recognize HEIC
from PIL import Image, ImageDraw, ImageFont

import importlib.resources

_FONT_PATH =  Path(str(importlib.resources.files(__package__) / 'fonts' /'Arimo-VariableFont_wght.ttf'))
#_FONT_PATH =  importlib.resources.files('fonts') / 'Arimo-VariableFont_wght.ttf'


def heic_to_jpeg(input_path, output_path, lat, lon):
    # Open HEIC image and convert it to RGB JPEG format
    with Image.open(input_path) as img:
        img = img.convert("RGB")

        # Prepare latitude and longitude footer text
        # Format latitude and longitude with N/S and E/W indicators
        lat = float(lat)
        lon = float(lon)
        lat_hemisphere = "N" if lat >= 0 else "S"
        lon_hemisphere = "E" if lon >= 0 else "W"
        formatted_lat = f"{abs(lat):.2f}° {lat_hemisphere}"
        formatted_lon = f"{abs(lon):.2f}° {lon_hemisphere}"
        footer_text = f"Latitude: {formatted_lat}, Longitude: {formatted_lon}"

        # Set up the font and size
        font_size = int(min(img.size) * 0.03)  # 3% of the image size
        #font = ImageFont.truetype("/Library/Fonts/Arial.ttf", font_size)
        font = ImageFont.truetype(_FONT_PATH.as_posix(), font_size)

        # Calculate the size of the footer text
        draw = ImageDraw.Draw(img)
        text_bbox = draw.textbbox((0, 0), footer_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        # Create a new image with extra space for the footer
        footer_height = text_height + 20  # Add padding around text
        new_img = Image.new("RGB", (img.width, img.height + footer_height), "white")
        new_img.paste(img, (0, 0))  # Paste original image on top

        # Draw the footer text on the white footer area
        draw = ImageDraw.Draw(new_img)
        text_position = ((new_img.width - text_width) // 2, img.height + 10)
        draw.text(text_position, footer_text, font=font, fill="black")

        # Save the new image with the footer as a JPEG
        new_img.save(output_path, "JPEG")
        print(f"Saved image to {output_path}")



def get_exif_data(file_path):
    # Get metadata using exiftool
    result = subprocess.run(
        ["exiftool", "-n", "-GPSLatitude", "-GPSLongitude", file_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    # Parse latitude and longitude from exiftool output
    lat, lon = None, None
    for line in result.stdout.splitlines():
        if "GPS Latitude" in line:
            lat = line.split(":")[1].strip()
        elif "GPS Longitude" in line:
            lon = line.split(":")[1].strip()
    
    return lat, lon

def convert_heic_images(input_dir, output_dir):
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each HEIC file in the input directory
    for file_name in os.listdir(input_dir):
        if file_name.lower().endswith(".heic"):
            input_path = os.path.join(input_dir, file_name)
            output_name = os.path.splitext(file_name)[0] + ".jpg"
            output_path = os.path.join(output_dir, output_name)
            
            # Get latitude and longitude using exiftool
            lat, lon = get_exif_data(input_path)
            
            # Skip files without GPS data
            if lat is None or lon is None:
                print(f"{file_name} missing lat or lon",file=sys.stderr)
                continue
            
            # Convert and save the image with the footer
            heic_to_jpeg(input_path, output_path, lat, lon)

def main():
    if not _FONT_PATH.is_file():
        raise FileNotFoundError(_FONT_PATH.as_posix())
    parser = argparse.ArgumentParser(description="Convert HEIC images to JPEG with GPS footer")
    parser.add_argument("input_dir", help="Input directory containing HEIC files")
    parser.add_argument("output_dir", help="Output directory for converted JPEG files")
    
    args = parser.parse_args()
    
    convert_heic_images(args.input_dir, args.output_dir)

if __name__ == "__main__":
    main()

