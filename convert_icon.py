"""
convert_icon.py - Retire le fond et genere mouseflow.ico
"""
from PIL import Image
from collections import deque
import os

# Trouve le PNG
for f in ["Mouseflow_icon.png", "Mouseflow icon.png", "mouseflow_icon.png"]:
    if os.path.exists(f):
        src_file = f
        break
else:
    print("ERREUR: PNG introuvable:", os.listdir("."))
    exit(1)

print(f"Chargement: {src_file}")
src = Image.open(src_file).convert("RGBA")
w, h = src.size
pixels = src.load()

# Flood fill depuis les bords - retire fond gris ou blanc
visited = [[False]*h for _ in range(w)]
queue = deque()
for x in range(w): queue.append((x,0)); queue.append((x,h-1))
for y in range(h): queue.append((0,y)); queue.append((w-1,y))

count = 0
while queue:
    x, y = queue.popleft()
    if x<0 or x>=w or y<0 or y>=h or visited[x][y]: continue
    visited[x][y] = True
    r, g, b, a = pixels[x, y]
    diff = max(abs(r-g), abs(g-b), abs(r-b))
    brightness = (r+g+b)//3
    if diff < 30 and brightness > 80:
        pixels[x, y] = (0, 0, 0, 0)
        count += 1
        for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx,ny = x+dx,y+dy
            if 0<=nx<w and 0<=ny<h and not visited[nx][ny]:
                queue.append((nx,ny))

print(f"Fond retire: {count} pixels")

sizes = [16, 32, 48, 64, 96, 128, 256]
frames = [src.resize((s,s), Image.LANCZOS) for s in sizes]
frames[0].save("mouseflow.ico", format="ICO",
               append_images=frames[1:], sizes=[(s,s) for s in sizes])
print(f"mouseflow.ico: {os.path.getsize('mouseflow.ico')} bytes")
