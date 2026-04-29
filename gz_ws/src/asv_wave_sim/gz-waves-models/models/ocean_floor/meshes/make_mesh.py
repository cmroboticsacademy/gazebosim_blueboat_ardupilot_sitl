#!/usr/bin/env python3
import os
import math
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEIGHTMAP_PATH = os.path.join(BASE_DIR, "../materials/textures/ocean_floor_heightmap.png")
OUTPUT_OBJ_PATH = os.path.join(BASE_DIR, "ocean_floor.obj")

SIZE_X = 100.0
SIZE_Y = 100.0
SIZE_Z = 5
STEP = 4

def normalize(v):
    x, y, z = v
    mag = math.sqrt(x * x + y * y + z * z)
    if mag < 1e-12:
        return (0.0, 0.0, 1.0)
    return (x / mag, y / mag, z / mag)

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )

def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

def main():
    img = Image.open(HEIGHTMAP_PATH).convert("L")
    width, height = img.size
    pixels = img.load()

    xs = list(range(0, width, STEP))
    ys = list(range(0, height, STEP))
    if xs[-1] != width - 1:
        xs.append(width - 1)
    if ys[-1] != height - 1:
        ys.append(height - 1)

    gw = len(xs)
    gh = len(ys)

    vertices = []
    faces = []
    vid = {}

    for j, py in enumerate(ys):
        for i, px in enumerate(xs):
            gray = pixels[px, py]
            z = (gray / 255.0) * SIZE_Z
            x = (px / (width - 1)) * SIZE_X - (SIZE_X / 2.0)
            y = (py / (height - 1)) * SIZE_Y - (SIZE_Y / 2.0)
            vertices.append((x, y, z))
            vid[(i, j)] = len(vertices)

    # Top surface only, with upward-facing winding
    for j in range(gh - 1):
        for i in range(gw - 1):
            v1 = vid[(i, j)]
            v2 = vid[(i + 1, j)]
            v3 = vid[(i, j + 1)]
            v4 = vid[(i + 1, j + 1)]
            faces.append((v1, v2, v3))
            faces.append((v2, v4, v3))

    normals = [(0.0, 0.0, 0.0) for _ in vertices]
    for a, b, c in faces:
        pa = vertices[a - 1]
        pb = vertices[b - 1]
        pc = vertices[c - 1]
        n = cross(sub(pb, pa), sub(pc, pa))
        normals[a - 1] = add(normals[a - 1], n)
        normals[b - 1] = add(normals[b - 1], n)
        normals[c - 1] = add(normals[c - 1], n)

    normals = [normalize(n) for n in normals]

    with open(OUTPUT_OBJ_PATH, "w", encoding="utf-8") as f:
        f.write("# ocean floor top-surface mesh\n")
        for x, y, z in vertices:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for nx, ny, nz in normals:
            f.write(f"vn {nx:.6f} {ny:.6f} {nz:.6f}\n")
        for a, b, c in faces:
            f.write(f"f {a}//{a} {b}//{b} {c}//{c}\n")

    print(f"Wrote {OUTPUT_OBJ_PATH}")
    print(f"Vertices: {len(vertices)}")
    print(f"Triangles: {len(faces)}")

if __name__ == "__main__":
    main()