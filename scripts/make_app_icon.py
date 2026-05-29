#!/usr/bin/env python3
"""Generate app icon assets from a source image.

Outputs:
- <assets-dir>/<name>.png
- <assets-dir>/<name>.ico
- <assets-dir>/<name>.icns (best effort)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PNG/ICO/ICNS app icons")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("specview_lg.png"),
        help="Path to source image (default: specview_lg.png)",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path("src/specview/assets"),
        help="Directory for generated icon files (default: src/specview/assets)",
    )
    parser.add_argument(
        "--name",
        default="specview",
        help="Base filename for outputs without extension (default: specview)",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=1024,
        help="Target square size for PNG/ICNS source (default: 1024)",
    )
    return parser.parse_args()


def _load_image_module():
    try:
        from PIL import Image
    except ModuleNotFoundError:
        print(
            "Pillow is required. Install with: uv add --dev pillow",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return Image


def _square_canvas(img, size: int):
    Image = _load_image_module()

    src = img.convert("RGBA")
    target = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Keep a little transparent margin so small icon sizes look cleaner.
    inner = int(size * 0.88)
    src.thumbnail((inner, inner), Image.Resampling.LANCZOS)

    x = (size - src.width) // 2
    y = (size - src.height) // 2
    target.paste(src, (x, y), src)
    return target


def main() -> int:
    args = parse_args()
    Image = _load_image_module()

    if not args.input.exists():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    if args.size < 256:
        print("--size should be at least 256 for good icon quality", file=sys.stderr)
        return 1

    args.assets_dir.mkdir(parents=True, exist_ok=True)

    png_path = args.assets_dir / f"{args.name}.png"
    ico_path = args.assets_dir / f"{args.name}.ico"
    icns_path = args.assets_dir / f"{args.name}.icns"

    with Image.open(args.input) as src:
        canvas = _square_canvas(src, args.size)

    canvas.save(png_path, format="PNG")

    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    canvas.save(ico_path, format="ICO", sizes=ico_sizes)

    icns_ok = True
    try:
        canvas.save(icns_path, format="ICNS")
    except OSError:
        icns_ok = False

    print(f"Wrote {png_path}")
    print(f"Wrote {ico_path}")
    if icns_ok:
        print(f"Wrote {icns_path}")
    else:
        print("Skipped ICNS (Pillow build does not support ICNS output on this platform)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
