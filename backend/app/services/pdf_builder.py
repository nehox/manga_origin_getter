from __future__ import annotations

from pathlib import Path

from PIL import Image


def build_pdf_from_images(image_paths: list[Path], output_pdf: Path) -> None:
    if not image_paths:
        raise ValueError("No images available for PDF build")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    opened: list[Image.Image] = []
    try:
        for image_path in sorted(image_paths):
            image = Image.open(image_path)
            if image.mode != "RGB":
                image = image.convert("RGB")
            opened.append(image)

        first, rest = opened[0], opened[1:]
        first.save(output_pdf, save_all=True, append_images=rest, format="PDF")
    finally:
        for image in opened:
            image.close()
