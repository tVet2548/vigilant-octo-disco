#!/usr/bin/env python3
"""Generate a clean multi-resolution Windows .ico file if assets/app.ico is missing."""
from pathlib import Path
import sys
from PIL import Image, ImageDraw


def generate_default_icon(output_path: Path) -> None:
    if output_path.exists():
        print(f"Using existing icon: {output_path}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded dark slate chassis
    draw.rounded_rectangle(
        [(12, 12), (size - 12, size - 12)],
        radius=52,
        fill=(15, 23, 42, 255),
        outline=(56, 189, 248, 255),
        width=8,
    )

    # Minimal geometric Android visor / kernel emblem
    draw.rounded_rectangle(
        [(56, 84), (size - 56, 184)],
        radius=28,
        fill=(30, 41, 59, 255),
        outline=(37, 99, 235, 255),
        width=6,
    )
    # Antennae
    draw.line([(86, 52), (104, 84)], fill=(56, 189, 248, 255), width=8)
    draw.line([(170, 52), (152, 84)], fill=(56, 189, 248, 255), width=8)
    # Eyes
    draw.ellipse([(88, 118), (112, 142)], fill=(56, 189, 248, 255))
    draw.ellipse([(144, 118), (168, 142)], fill=(56, 189, 248, 255))

    img.save(
        output_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated default icon at: {output_path}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets/app.ico")
    generate_default_icon(target)
