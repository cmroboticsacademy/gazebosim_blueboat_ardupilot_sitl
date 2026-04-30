#!/usr/bin/env python3
import os
import math
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Match the mesh builder path so the OBJ script reads the image this script writes.
OUT_PATH = os.path.join(
    BASE_DIR,
    "./ocean_floor_heightmap.png"
)

SIZE = 256
SEED = 42
random.seed(SEED)

BASE_LEVEL = 0.18

# Existing bump settings kept here, but disabled for first word-only test.
NUM_LARGE_BUMPS = 15
NUM_MEDIUM_BUMPS = 20
NUM_PITS = 1
ENABLE_WAVES = True

# Word bump settings
TEXT = "Cheeseburger"
TEXT_AMP = 0.65          # Height added by the word.
TEXT_MARGIN = 0.10       # Percentage padding around text.
TEXT_BLUR = 1.25         # Rounds/softens letter edges.
TEXT_POWER = 1.0         # Higher values make letters steeper/sharper.
MIRROR_TEXT_X = True     # Mirrors the word left-to-right.
INVERT_Y = False         # Set True if text appears upside down in your mesh.

def gaussian(x, y, cx, cy, amp, sigma):
    dx = x - cx
    dy = y - cy
    return amp * math.exp(-(dx * dx + dy * dy) / (2.0 * sigma * sigma))


def clamp01(v):
    return max(0.0, min(1.0, v))


def load_font(size):
    """
    Tries to load a bold TrueType font.
    Falls back to Pillow's default font if unavailable.
    """
    candidates = [
        "DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass

    return ImageFont.load_default()


def make_text_mask(text):
    """
    Creates a grayscale mask where white pixels represent raised text.
    """
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(mask)

    max_text_width = int(SIZE * (1.0 - TEXT_MARGIN * 2.0))
    max_text_height = int(SIZE * 0.45)

    font_size = SIZE

    while font_size > 4:
        font = load_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        if tw <= max_text_width and th <= max_text_height:
            break

        font_size -= 2

    font = load_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)

    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    x = (SIZE - tw) / 2.0 - bbox[0]
    y = (SIZE - th) / 2.0 - bbox[1]

    draw.text((x, y), text, fill=255, font=font)

    if TEXT_BLUR > 0.0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=TEXT_BLUR))

    if MIRROR_TEXT_X:
        mask = mask.transpose(Image.FLIP_LEFT_RIGHT)

    if INVERT_Y:
        mask = mask.transpose(Image.FLIP_TOP_BOTTOM)

    return mask


def main():
    img = Image.new("L", (SIZE, SIZE))
    pixels = img.load()

    text_mask = make_text_mask(TEXT)
    text_pixels = text_mask.load()

    features = []

    # ------------------------------------------------------------------
    # Existing random bumps would be re-enabled here after word-only test.
    # ------------------------------------------------------------------

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

            # ----------------------------------------------------------
            # Existing wave terrain would be re-enabled here later.
            # ----------------------------------------------------------
            if ENABLE_WAVES:
                v += 0.03 * math.sin(x * math.pi * 2.0)
                v += 0.025 * math.cos(y * math.pi * 2.5)
                v += 0.02 * math.sin((x + y) * math.pi * 1.5)

            # ----------------------------------------------------------
            # Existing bump terrain would be re-enabled here later.
            # ----------------------------------------------------------
            for cx, cy, amp, sigma in features:
                v += gaussian(x, y, cx, cy, amp, sigma)

            # Raised word bump
            text_t = text_pixels[px, py] / 255.0
            text_t = text_t ** TEXT_POWER
            v += text_t * TEXT_AMP

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
    print(f"Text: {TEXT}")
    print(f"Value range: {vmin:.6f} to {vmax:.6f}")


if __name__ == "__main__":
    main()