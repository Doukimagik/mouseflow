"""
Génère mouseflow.ico pendant le build GitHub Actions
"""
from PIL import Image, ImageDraw
import os

def make_frame(size):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Fond cercle bleu-noir
    d.ellipse([0, 0, s-1, s-1], fill=(18, 24, 32, 255))

    # Bordure bleue
    bw = max(1, s // 22)
    d.ellipse([bw, bw, s-1-bw, s-1-bw], outline=(88, 166, 255, 255), width=bw * 2)

    # Curseur flèche blanche
    if s >= 16:
        m = s // 5
        pts = [
            (m,         m),
            (m,         s - m),
            (m + s//8,  s - m - s//8),
            (m + s//5,  s - m + s//10),
            (m + s//4,  s - m),
            (m + s//6,  s - m - s//5),
            (m + s//3,  s - m - s//5),
        ]
        d.polygon(pts, fill=(220, 230, 255, 255))
        if s >= 48:
            d.polygon(pts, outline=(88, 166, 255, 180))

    # Point vert de tracking
    if s >= 32:
        r = max(2, s // 12)
        cx, cy = s * 3 // 4, s * 3 // 4
        # Halo
        d.ellipse([cx - r*2, cy - r*2, cx + r*2, cy + r*2],
                  fill=(63, 185, 80, 60))
        # Dot
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=(63, 185, 80, 255))

    return img

if __name__ == "__main__":
    sizes = [16, 32, 48, 64, 128, 256]
    frames = [make_frame(s) for s in sizes]

    frames[0].save(
        "mouseflow.ico",
        format="ICO",
        append_images=frames[1:],
        sizes=[(s, s) for s in sizes]
    )
    print(f"mouseflow.ico generee ({os.path.getsize('mouseflow.ico')} bytes)")
