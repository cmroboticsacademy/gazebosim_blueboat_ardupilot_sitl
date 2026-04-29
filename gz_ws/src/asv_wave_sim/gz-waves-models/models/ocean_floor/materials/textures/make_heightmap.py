#!/usr/bin/env python3
import os
import math
import random
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, "./ocean_floor_heightmap.png")

SIZE = 256
SEED = 42
random.seed(SEED)

BASE_LEVEL = 0.18
NUM_LARGE_BUMPS = 50
NUM_MEDIUM_BUMPS = 1000
NUM_PITS = 0

ENABLE_WAVES = False

def gaussian(x, y, cx, cy, amp, sigma):
    dx = x - cx
    dy = y - cy
    return amp * math.exp(-(dx * dx + dy * dy) / (2.0 * sigma * sigma))

def clamp01(v):
    return max(0.0, min(1.0, v))

def main():
    img = Image.new("L", (SIZE, SIZE))
    pixels = img.load()

    features = []

    for _ in range(NUM_LARGE_BUMPS):
        cx = random.uniform(0.10, 0.90)
        cy = random.uniform(0.10, 0.90)
        amp = random.uniform(0.18, 0.40)
        sigma = random.uniform(0.05, 0.12)
        features.append((cx, cy, amp, sigma))

    for _ in range(NUM_MEDIUM_BUMPS):
        cx = random.uniform(0.05, 0.95)
        cy = random.uniform(0.05, 0.95)
        amp = random.uniform(0.06, 0.16)
        sigma = random.uniform(0.02, 0.05)
        features.append((cx, cy, amp, sigma))

    for _ in range(NUM_PITS):
        cx = random.uniform(0.10, 0.90)
        cy = random.uniform(0.10, 0.90)
        amp = -random.uniform(0.05, 0.14)
        sigma = random.uniform(0.03, 0.07)
        features.append((cx, cy, amp, sigma))

    values = []
    for py in range(SIZE):
        for px in range(SIZE):
            x = px / (SIZE - 1)
            y = py / (SIZE - 1)

            v = BASE_LEVEL

            if ENABLE_WAVES:
                v += 0.03 * math.sin(x * math.pi * 2.0)
                v += 0.025 * math.cos(y * math.pi * 2.5)
                v += 0.02 * math.sin((x + y) * math.pi * 1.5)

            for cx, cy, amp, sigma in features:
                v += gaussian(x, y, cx, cy, amp, sigma)

            values.append(v)

    vmin = min(values)
    vmax = max(values)

    i = 0
    for py in range(SIZE):
        for px in range(SIZE):
            if abs(vmax - vmin) < 1e-12:
                t = 0.5
            else:
                t = (values[i] - vmin) / (vmax - vmin)
            i += 1

            t = clamp01(t)
            gray = int(round(255 * t))
            pixels[px, py] = gray

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    img.save(OUT_PATH)
    print(f"Wrote {OUT_PATH}")
    print(f"Image size: {SIZE} x {SIZE}")
    print(f"Value range: {vmin:.6f} to {vmax:.6f}")

if __name__ == "__main__":
    main()