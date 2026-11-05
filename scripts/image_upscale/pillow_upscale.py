"""Isolated Pillow renderer. No application configuration or database imports."""
import io
import sys
import warnings

from PIL import Image, ImageOps


def main():
    width, height, fit = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    if not (0 < width <= 8192 and 0 < height <= 8192 and width * height <= 32 * 1024 * 1024 and fit in {"contain", "cover"}):
        raise ValueError("Invalid target")
    data = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024:
        raise ValueError("Input limit")
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    with Image.open(io.BytesIO(data)) as source:
        if source.width * source.height > 32 * 1024 * 1024 or getattr(source, "is_animated", False):
            raise ValueError("Unsupported source")
        fmt = str(source.format or "PNG").upper()
        image = ImageOps.exif_transpose(source)
        alpha = "A" in image.getbands() or "transparency" in image.info
        image = image.convert("RGBA" if alpha else "RGB")
        if fit == "contain":
            output = ImageOps.pad(image, (width, height), method=Image.Resampling.LANCZOS, color=(0, 0, 0, 0) if alpha else "white")
        else:
            output = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        options = {}
        if fmt in {"JPG", "JPEG"}:
            fmt = "JPEG"
            options = {"quality": 95, "subsampling": 0}
            output = output.convert("RGB")
        elif fmt == "WEBP":
            options = {"quality": 95, "method": 3}
        else:
            fmt = "PNG"
            options = {"compress_level": 3}
        output.save(buffer, format=fmt, **options)
        sys.stdout.buffer.write(buffer.getvalue())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("Pillow enlargement failed")
        sys.exit(1)
