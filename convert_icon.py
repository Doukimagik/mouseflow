"""
convert_icon.py - Convertit file.svg en mouseflow.ico
Utilise svglib + reportlab (pur Python, compatible Windows)
"""
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM
from PIL import Image
import io, os

svg_file = "file.svg"

if not os.path.exists(svg_file):
    print(f"ERREUR: {svg_file} introuvable")
    exit(1)

print(f"Conversion de {svg_file}...")
drawing = svg2rlg(svg_file)
print(f"SVG: {drawing.width}x{drawing.height}")

sizes = [16, 24, 32, 48, 64, 128, 256]
frames = []

for s in sizes:
    scale_x = s / drawing.width
    scale_y = s / drawing.height
    drawing.width = s
    drawing.height = s
    drawing.transform = (scale_x, 0, 0, scale_y, 0, 0)
    buf = io.BytesIO()
    renderPM.drawToFile(drawing, buf, fmt="PNG", dpi=96)
    buf.seek(0)
    frame = Image.open(buf).convert("RGBA").resize((s, s), Image.LANCZOS)
    frames.append(frame)
    print(f"  {s}x{s} OK")

frames[0].save("mouseflow.ico", format="ICO",
               append_images=frames[1:],
               sizes=[(s, s) for s in sizes])
print(f"mouseflow.ico genere ({os.path.getsize('mouseflow.ico')} bytes)")
