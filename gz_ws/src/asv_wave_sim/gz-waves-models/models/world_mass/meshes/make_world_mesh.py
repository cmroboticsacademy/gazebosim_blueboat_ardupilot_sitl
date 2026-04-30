#!/usr/bin/env python3
import math
import os
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HEIGHTMAP_PATH = os.path.join(BASE_DIR, "../materials/textures/world_heightmap.png")
OBJ_PATH = os.path.normpath(os.path.join(BASE_DIR, "./world_land.obj"))
MTL_PATH = os.path.normpath(os.path.join(BASE_DIR, "./world_land.mtl"))

# Mirror the sampled raster, not the mesh geometry.
# Start with MIRROR_Y = True based on your description.
MIRROR_X = False
MIRROR_Y = True

# Full terrain size in meters
SIZE_X = 500.0
SIZE_Y = 500.0

# Vertical placement
BOTTOM_Z = 0
TOP_MIN_Z = -20
TOP_MAX_Z = 10

STEP = 8

MTL_NAME = "world_land_mat"
TEXTURE_REL_PATH = "../materials/textures/world_lightmap.png"


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


def add_face(faces, a, b, c):
    faces.append((a, b, c))


def sample_indices(length, step):
    vals = list(range(0, length, step))
    if vals[-1] != length - 1:
        vals.append(length - 1)
    return vals


def pixel_to_world(px, py, width, height):
    # Keep the stable world mapping from your current version.
    # Do NOT mirror here.
    x = ((px / (width - 1)) - 0.5) * SIZE_X
    y = ((py / (height - 1)) - 0.5) * SIZE_Y
    return x, y


def sample_pixel(px, py, width, height):
    sx = (width - 1 - px) if MIRROR_X else px
    sy = (height - 1 - py) if MIRROR_Y else py
    return sx, sy


def main():
    img = Image.open(HEIGHTMAP_PATH).convert("L")
    width, height = img.size
    pixels = img.load()

    xs = sample_indices(width, STEP)
    ys = sample_indices(height, STEP)

    gw = len(xs)
    gh = len(ys)

    vertices = []
    uvs = []
    faces = []

    top_ids = {}
    bot_ids = {}

    # Top surface
    for j, py in enumerate(ys):
        for i, px in enumerate(xs):
            sx, sy = sample_pixel(px, py, width, height)

            gray = pixels[sx, sy]
            t = gray / 255.0

            x, y = pixel_to_world(px, py, width, height)
            z = TOP_MIN_Z + t * (TOP_MAX_Z - TOP_MIN_Z)

            u = sx / (width - 1)
            v = 1.0 - (sy / (height - 1))

            vertices.append((x, y, z))
            uvs.append((u, v))
            top_ids[(i, j)] = len(vertices)

    # Bottom surface
    for j, py in enumerate(ys):
        for i, px in enumerate(xs):
            x, y = pixel_to_world(px, py, width, height)
            z = BOTTOM_Z

            # Bottom UVs can stay in unmirrored mesh space
            u = px / (width - 1)
            v = 1.0 - (py / (height - 1))

            vertices.append((x, y, z))
            uvs.append((u, v))
            bot_ids[(i, j)] = len(vertices)

    # Top
    for j in range(gh - 1):
        for i in range(gw - 1):
            v1 = top_ids[(i, j)]
            v2 = top_ids[(i + 1, j)]
            v3 = top_ids[(i, j + 1)]
            v4 = top_ids[(i + 1, j + 1)]
            add_face(faces, v1, v2, v3)
            add_face(faces, v2, v4, v3)

    # Bottom
    for j in range(gh - 1):
        for i in range(gw - 1):
            v1 = bot_ids[(i, j)]
            v2 = bot_ids[(i + 1, j)]
            v3 = bot_ids[(i, j + 1)]
            v4 = bot_ids[(i + 1, j + 1)]
            add_face(faces, v1, v3, v2)
            add_face(faces, v2, v3, v4)

    # North edge
    for i in range(gw - 1):
        t1 = top_ids[(i, 0)]
        t2 = top_ids[(i + 1, 0)]
        b1 = bot_ids[(i, 0)]
        b2 = bot_ids[(i + 1, 0)]
        add_face(faces, t1, b1, t2)
        add_face(faces, t2, b1, b2)

    # South edge
    for i in range(gw - 1):
        t1 = top_ids[(i, gh - 1)]
        t2 = top_ids[(i + 1, gh - 1)]
        b1 = bot_ids[(i, gh - 1)]
        b2 = bot_ids[(i + 1, gh - 1)]
        add_face(faces, t1, t2, b1)
        add_face(faces, t2, b2, b1)

    # West edge
    for j in range(gh - 1):
        t1 = top_ids[(0, j)]
        t2 = top_ids[(0, j + 1)]
        b1 = bot_ids[(0, j)]
        b2 = bot_ids[(0, j + 1)]
        add_face(faces, t1, t2, b1)
        add_face(faces, t2, b2, b1)

    # East edge
    for j in range(gh - 1):
        t1 = top_ids[(gw - 1, j)]
        t2 = top_ids[(gw - 1, j + 1)]
        b1 = bot_ids[(gw - 1, j)]
        b2 = bot_ids[(gw - 1, j + 1)]
        add_face(faces, t1, b1, t2)
        add_face(faces, t2, b1, b2)

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

    os.makedirs(os.path.dirname(OBJ_PATH), exist_ok=True)

    with open(MTL_PATH, "w", encoding="utf-8") as f:
        f.write(f"newmtl {MTL_NAME}\n")
        f.write("Ka 1.000 1.000 1.000\n")
        f.write("Kd 1.000 1.000 1.000\n")
        f.write("Ks 0.000 0.000 0.000\n")
        f.write("d 1.0\n")
        f.write("illum 1\n")
        f.write(f"map_Kd {TEXTURE_REL_PATH}\n")

    with open(OBJ_PATH, "w", encoding="utf-8") as f:
        f.write("mtllib world_land.mtl\n")
        f.write(f"usemtl {MTL_NAME}\n")

        for x, y, z in vertices:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")

        for u, v in uvs:
            f.write(f"vt {u:.6f} {v:.6f}\n")

        for nx, ny, nz in normals:
            f.write(f"vn {nx:.6f} {ny:.6f} {nz:.6f}\n")

        for a, b, c in faces:
            f.write(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n")

    print(f"Wrote {OBJ_PATH}")
    print(f"Wrote {MTL_PATH}")
    print(f"Terrain centered at world origin")
    print(f"Size: {SIZE_X} x {SIZE_Y}")
    print(f"Mirror flags: MIRROR_X={MIRROR_X}, MIRROR_Y={MIRROR_Y}")


if __name__ == "__main__":
    main()