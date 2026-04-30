"""
Generates extension icons (icon16.png, icon48.png, icon128.png) into extension/

To use the official Claude logo:
  1. Save the Claude logo as claude_logo_source.png in this folder (1:1 square crop)
  2. Run: python make_icons.py
  It will resize and use your image instead of the generated fallback.

Without a source image, generates an orange "C" icon approximating the Claude brand.
"""
from PIL import Image, ImageDraw
from pathlib import Path
import math

ORANGE = (218, 119, 86)
WHITE  = (255, 255, 255)
OUT    = Path(__file__).parent / "extension"
SRC    = Path(__file__).parent / "claude_logo_source.png"


def make_generated_icon(size: int) -> Image.Image:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded square background
    corner = size // 5
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=corner, fill=ORANGE)

    # White "C" arc — Claude brand mark
    pad    = size * 0.20
    cx, cy = size / 2, size / 2
    radius = size / 2 - pad
    arc_w  = max(2, size // 9)
    bbox   = [cx - radius, cy - radius, cx + radius, cy + radius]
    draw.arc(bbox, start=40, end=320, fill=WHITE, width=arc_w)

    return img


def make_icon(size: int) -> Image.Image:
    if SRC.exists():
        src = Image.open(SRC).convert("RGBA")
        return src.resize((size, size), Image.LANCZOS)
    return make_generated_icon(size)


for px in (16, 48, 128):
    icon = make_icon(px)
    path = OUT / f"icon{px}.png"
    icon.save(path)
    print(f"Saved {path}")

# ICO for the Windows .exe — start from 256px, Pillow downsamples each size
ico_base = make_icon(256)
ico_path = Path(__file__).parent / "icon.ico"
ico_base.save(ico_path, format="ICO",
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Saved {ico_path}")

print()
if SRC.exists():
    print(f"Used custom logo: {SRC}")
else:
    print("No claude_logo_source.png found -- used generated icon.")
    print("To use Claude's official logo, save it as claude_logo_source.png and rerun.")
print("Reload the extension at chrome://extensions to see updated icons.")
