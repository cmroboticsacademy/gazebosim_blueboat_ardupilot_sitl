#!/usr/bin/env python3
import os
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEIGHTMAP_PATH = os.path.join(
    BASE_DIR, "../materials/textures/ocean_floor_heightmap.png"
)
OUTPUT_OBJ_PATH = os.path.join(BASE_DIR, "ocean_floor.obj")

SIZE_X = 50.0
SIZE_Y = 50.0
SIZE_Z = 2.5
THICKNESS = 1.0
STEP = 6

def add_face(faces, a, b, c):
    faces.append((a, b, c))

def main():
    img = Image.open(HEIGHTMAP_PATH).convert("L")
    width, height = img.size
    px = img.load()

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

    # top surface vertices
    top_ids = {}
    for j, py in enumerate(ys):
        for i, px_i in enumerate(xs):
            gray = px[px_i, py]
            z = (gray / 255.0) * SIZE_Z
            x = (px_i / (width - 1)) * SIZE_X - SIZE_X / 2.0
            y = (py / (height - 1)) * SIZE_Y - SIZE_Y / 2.0
            vertices.append((x, y, z))
            top_ids[(i, j)] = len(vertices)

    # bottom surface vertices
    bottom_z = -THICKNESS
    bottom_ids = {}
    for j, py in enumerate(ys):
        for i, px_i in enumerate(xs):
            x = (px_i / (width - 1)) * SIZE_X - SIZE_X / 2.0
            y = (py / (height - 1)) * SIZE_Y - SIZE_Y / 2.0
            vertices.append((x, y, bottom_z))
            bottom_ids[(i, j)] = len(vertices)

    # top surface triangles
    for j in range(gh - 1):
        for i in range(gw - 1):
            v1 = top_ids[(i, j)]
            v2 = top_ids[(i + 1, j)]
            v3 = top_ids[(i, j + 1)]
            v4 = top_ids[(i + 1, j + 1)]
            add_face(faces, v1, v3, v2)
            add_face(faces, v2, v3, v4)

    # bottom surface triangles (reversed)
    for j in range(gh - 1):
        for i in range(gw - 1):
            v1 = bottom_ids[(i, j)]
            v2 = bottom_ids[(i + 1, j)]
            v3 = bottom_ids[(i, j + 1)]
            v4 = bottom_ids[(i + 1, j + 1)]
            add_face(faces, v1, v2, v3)
            add_face(faces, v2, v4, v3)

    # side walls: top edge
    for i in range(gw - 1):
        t1 = top_ids[(i, 0)]
        t2 = top_ids[(i + 1, 0)]
        b1 = bottom_ids[(i, 0)]
        b2 = bottom_ids[(i + 1, 0)]
        add_face(faces, t1, b1, t2)
        add_face(faces, t2, b1, b2)

    # bottom edge
    for i in range(gw - 1):
        t1 = top_ids[(i, gh - 1)]
        t2 = top_ids[(i + 1, gh - 1)]
        b1 = bottom_ids[(i, gh - 1)]
        b2 = bottom_ids[(i + 1, gh - 1)]
        add_face(faces, t1, t2, b1)
        add_face(faces, t2, b2, b1)

    # left edge
    for j in range(gh - 1):
        t1 = top_ids[(0, j)]
        t2 = top_ids[(0, j + 1)]
        b1 = bottom_ids[(0, j)]
        b2 = bottom_ids[(0, j + 1)]
        add_face(faces, t1, t2, b1)
        add_face(faces, t2, b2, b1)

    # right edge
    for j in range(gh - 1):
        t1 = top_ids[(gw - 1, j)]
        t2 = top_ids[(gw - 1, j + 1)]
        b1 = bottom_ids[(gw - 1, j)]
        b2 = bottom_ids[(gw - 1, j + 1)]
        add_face(faces, t1, b1, t2)
        add_face(faces, t2, b1, b2)

    with open(OUTPUT_OBJ_PATH, "w", encoding="utf-8") as f:
        f.write("# watertight ocean floor slab mesh\n")
        for x, y, z in vertices:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            f.write(f"f {a} {b} {c}\n")

    print(f"Wrote {OUTPUT_OBJ_PATH}")
    print(f"Vertices: {len(vertices)}")
    print(f"Triangles: {len(faces)}")

if __name__ == "__main__":
    main()