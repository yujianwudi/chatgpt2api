"""Isolated Pillow renderer. No application configuration or database imports."""
import io
import hashlib
import json
import sys
import warnings

from PIL import Image, ImageOps


def main_gif():
    width, height = int(sys.argv[1]), int(sys.argv[2])
    expected_frames, duration = int(sys.argv[5]), int(sys.argv[6])
    raw = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("input_byte_limit")
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    frames, durations, distinct = [], [], set()
    with Image.open(io.BytesIO(raw)) as source:
        if source.format != "GIF" or not 2 <= source.n_frames <= 60:
            raise ValueError("not_a_bounded_animation")
        count = source.n_frames
        if expected_frames and expected_frames != count:
            raise ValueError(f"frame_count_mismatch: expected {expected_frames}, received {count}")
        original_size = source.size
        target = (width, height) if width and height else original_size
        if (min(target) <= 0 or max(target) > 2048
                or count * max(source.width * source.height, target[0] * target[1]) > 32 * 1024 * 1024):
            raise ValueError("pixel_limit")
        loop = source.info.get("loop")
        transparent = "transparency" in source.info
        for index in range(count):
            source.seek(index)
            frame = source.convert("RGBA")
            distinct.add(hashlib.sha256(frame.tobytes()).digest())
            durations.append(duration or int(source.info.get("duration", 0)))
            if not 10 <= durations[-1] <= 60000 or durations[-1] % 10:
                raise ValueError("unsupported_frame_duration")
            if target != original_size:
                frame = ImageOps.pad(frame, target, method=Image.Resampling.LANCZOS,
                                     color=(0, 0, 0, 0) if transparent else (255, 255, 255, 255))
            frames.append(frame if transparent else frame.convert("RGB"))
        if len(distinct) < 2:
            raise ValueError("animation_has_no_frame_changes")
        source.seek(0)
        original_durations = []
        for index in range(count):
            source.seek(index)
            original_durations.append(int(source.info.get("duration", 0)))
    changed = target != original_size or durations != original_durations
    result = raw
    if changed:
        buffer = io.BytesIO()
        options = {"loop": loop} if loop is not None else {}
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:],
                       duration=durations, disposal=2, optimize=False, **options)
        result = buffer.getvalue()
    if len(result) > 64 * 1024 * 1024:
        raise ValueError("output_byte_limit")
    with Image.open(io.BytesIO(result)) as check:
        if check.size != target or check.n_frames != count or check.info.get("loop") != loop:
            raise ValueError("encoded_animation_mismatch")
        for index in range(count):
            check.seek(index)
            if check.info.get("duration", 0) != durations[index]:
                raise ValueError("encoded_duration_mismatch")
    sys.stdout.buffer.write(result)
    sys.stderr.write(json.dumps({"operation": "gif_canvas_and_timing" if changed else "gif_validation",
                                "source_size": list(original_size), "output_size": list(target),
                                "frame_count": count, "frame_durations_ms": durations,
                                "loop": loop, "reencoded": changed}))


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
        main_gif() if len(sys.argv) > 4 and sys.argv[4] == "gif" else main()
    except Exception as exc:
        if len(sys.argv) > 4 and sys.argv[4] == "gif":
            sys.stderr.write(json.dumps({"error": str(exc) if type(exc) is ValueError else "invalid_animation"}))
        else:
            sys.stderr.write("Pillow enlargement failed")
        sys.exit(1)
