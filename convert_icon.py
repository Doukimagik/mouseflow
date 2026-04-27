"""
convert_icon.py
Convertit file.svg en mouseflow.ico
Execute pendant le build GitHub Actions
"""
import cairosvg
import io
import os
from PIL import Image

svg_file = "file.svg"

if not os.path.exists(svg_file):
    print(f"ERREUR: {svg_file} introuvable !")
    exit(1)

print(f"Conversion de {svg_file} en mouseflow.ico...")

sizes = [16, 24, 32, 48, 64, 128, 256]
frames = []

for s in sizes:
    png_data = cairosvg.svg2png(url=svg_file, output_width=s, output_height=s)
    frame = Image.open(io.BytesIO(png_data)).convert("RGBA")
    frames.append(frame)
    print(f"  {s}x{s} rendu OK")

frames[0].save(
    "mouseflow.ico",
    format="ICO",
    append_images=frames[1:],
    sizes=[(s, s) for s in sizes]
)

size = os.path.getsize("mouseflow.ico")
print(f"mouseflow.ico genere avec succes ({size} bytes)")
