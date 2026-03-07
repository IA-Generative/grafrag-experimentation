from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "bridge" / "assets"
SOURCE_NAME = "mirai-graphrag.png"
SOURCE_PATH = ASSET_DIR / SOURCE_NAME


def load_source_image() -> Image.Image:
    if not SOURCE_PATH.exists():
        raise SystemExit(f"Source brand image not found: {SOURCE_PATH}")
    return Image.open(SOURCE_PATH).convert("RGBA")


def resized_copy(image: Image.Image, size: int) -> Image.Image:
    resized = image.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 64:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=1.0, percent=175, threshold=2))
    return resized


def save_png(image: Image.Image, path: Path, size: int) -> None:
    resized_copy(image, size).save(path, format="PNG")


def avatar_copy(image: Image.Image, size: int) -> Image.Image:
    # Focus the crop on the mascot rather than the full scene for model avatars.
    avatar = ImageOps.fit(
        image,
        (size, size),
        method=Image.Resampling.LANCZOS,
        centering=(0.34, 0.42),
    )
    if size <= 128:
        avatar = avatar.filter(
            ImageFilter.UnsharpMask(radius=1.0, percent=180, threshold=2)
        )
    return avatar


def save_avatar(image: Image.Image, path: Path, size: int) -> None:
    avatar_copy(image, size).save(path, format="PNG")


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    source = load_source_image()

    compatibility_aliases = {
        "mirai-hero-1024.png": 1024,
        "mirai-hero-512.png": 512,
        "mirai-hero-256.png": 256,
        "mirai-icon-512.png": 512,
    }
    source_derivatives = {
        "mirai-graphrag-512.png": 512,
        "mirai-graphrag-256.png": 256,
        "mirai-model-avatar-256.png": 256,
        "mirai-model-avatar-128.png": 128,
        "mirai-model-avatar-64.png": 64,
        "android-chrome-512x512.png": 512,
        "android-chrome-192x192.png": 192,
        "apple-touch-icon.png": 180,
        "favicon-32x32.png": 32,
        "favicon-16x16.png": 16,
    }

    for filename, size in {**compatibility_aliases, **source_derivatives}.items():
        if filename.startswith("mirai-model-avatar-"):
            save_avatar(source, ASSET_DIR / filename, size)
        else:
            save_png(source, ASSET_DIR / filename, size)

    resized_copy(source, 64).save(
        ASSET_DIR / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64)],
    )

    manifest = {
        "name": "MirAI Graph Viewer",
        "short_name": "MirAI",
        "icons": [
            {"src": "/assets/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/assets/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": "#000091",
        "background_color": "#f6f6f6",
        "display": "standalone",
    }
    (ASSET_DIR / "site.webmanifest").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
