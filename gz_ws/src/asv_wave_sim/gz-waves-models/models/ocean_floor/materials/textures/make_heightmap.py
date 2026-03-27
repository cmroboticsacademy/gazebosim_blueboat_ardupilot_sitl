#!/usr/bin/env python3
from PIL import Image
import math
import random

SIZE = 513
SEED = 42
random.seed(SEED)

def fbm(x, y, octaves=5):
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    norm = 0.0

    for _ in range(octaves):
        total += amplitude * (
            math.sin((x * frequency) * 2.1) * 0.35 +
            math.cos((y * frequency) * 1.7) * 0.35 +
            math.sin((x + y) * frequency * 1.3) * 0.20 +
            math.cos((x - y) * frequency * 2.7) * 0.10
        )
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.0

    return total / norm

def gaussian_feature(x, y, cx, cy, amp, sigma):
    dx = x - cx
    dy = y - cy
    return amp * math.exp(-(dx * dx + dy * dy) / (2.0 * sigma * sigma))

img = Image.new("L", (SIZE, SIZE))
pixels = img.load()

features = []

# Many small positive bumps
for _ in range(80):
    cx = random.uniform(0, 1)
    cy = random.uniform(0, 1)
    amp = random.uniform(0.08, 0.22)
    sigma = random.uniform(0.015, 0.05)
    features.append((cx, cy, amp, sigma))

# Many small negative ravines / pits
for _ in range(70):
    cx = random.uniform(0, 1)
    cy = random.uniform(0, 1)
    amp = -random.uniform(0.08, 0.25)
    sigma = random.uniform(0.015, 0.06)
    features.append((cx, cy, amp, sigma))

values = []

for py in range(SIZE):
    for px in range(SIZE):
        x = px / (SIZE - 1)
        y = py / (SIZE - 1)

        # Flat baseline
        v = 0.5

        # Broad distributed roughness
        v += 0.10 * fbm(x * 6.0, y * 6.0, octaves=5)

        # Fine texture everywhere
        v += 0.03 * math.sin(x * 60.0)
        v += 0.03 * math.cos(y * 55.0)
        v += 0.02 * math.sin((x + y) * 75.0)

        # Scattered bumps and pits everywhere
        for cx, cy, amp, sigma in features:
            v += gaussian_feature(x, y, cx, cy, amp, sigma)

        values.append(v)

vmin = min(values)
vmax = max(values)

i = 0
for py in range(SIZE):
    for px in range(SIZE):
        v = values[i]
        i += 1
        gray = int(255 * (v - vmin) / (vmax - vmin))
        pixels[px, py] = max(0, min(255, gray))

img.save("ocean_floor_heightmap.png")
print("Wrote ocean_floor_heightmap.png")