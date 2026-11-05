from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path

from PIL import Image

from services.config import config
from utils.log import logger


_WORKERS = Path(__file__).resolve().parents[1] / "scripts" / "image_upscale"
_UPSCALE_SLOTS = threading.BoundedSemaphore(2)
_MAX_DIMENSION = 8192
_MAX_PIXELS = 32 * 1024 * 1024
_MAX_INPUT_BYTES = 32 * 1024 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024 * 1024
_QUEUE_SECONDS = 5.0
_TOTAL_SECONDS = 60.0
_RETURN_RESERVE_SECONDS = 2.0


class _UpscaleError(RuntimeError):
    pass


def _target_size(value: object) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{2,5})\s*x\s*(\d{2,5})", str(value or "").strip().lower())
    if not match:
        return None
    width, height = int(match[1]), int(match[2])
    if not (0 < width <= _MAX_DIMENSION and 0 < height <= _MAX_DIMENSION):
        return None
    return width, height


def _inspect_image(data: bytes) -> tuple[tuple[int, int], bool]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width * height > _MAX_PIXELS:
                raise _UpscaleError("source_pixel_limit")
            if image.getexif().get(274) in {5, 6, 7, 8}:
                width, height = height, width
            return (width, height), bool(getattr(image, "is_animated", False))


def _render(engine: str, data: bytes, target: tuple[int, int], fit: str, deadline: float) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _UpscaleError("processing_timeout")
    if engine == "sharp_lanczos3":
        node = shutil.which("node")
        if not node:
            raise _UpscaleError("runtime_unavailable")
        command = [node, str(_WORKERS / "upscale.mjs")]
    else:
        command = [sys.executable, str(_WORKERS / "pillow_upscale.py")]
    completed = subprocess.run(
        command + [str(target[0]), str(target[1]), fit],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=remaining, check=False,
    )
    if completed.returncode or not completed.stdout:
        raise _UpscaleError("engine_failed")
    result = completed.stdout
    if len(result) > _MAX_OUTPUT_BYTES:
        raise _UpscaleError("output_byte_limit")
    # Workers normalize orientation. Verify the encoded file without decoding
    # the same output pixels a second time in the application process.
    with Image.open(io.BytesIO(result)) as image:
        if image.size != target or getattr(image, "is_animated", False):
            raise _UpscaleError("invalid_output")
        image.verify()
    if time.monotonic() > deadline:
        raise _UpscaleError("processing_timeout")
    return result


def upscale_image_if_needed(
    image_data: bytes,
    requested_size: object,
    *,
    deadline_monotonic: float | None = None,
    call_id: str | None = None,
    report: dict[str, object] | None = None,
) -> bytes:
    """Optional best-effort interpolation; every unsuccessful path retains input."""
    if not image_data or not config.image_upscale_enabled:
        return image_data
    # GIF output must remain byte-for-byte unchanged; Pillow/Sharp would
    # otherwise collapse an animated image into a single raster frame.
    if image_data.startswith((b"GIF87a", b"GIF89a")):
        return image_data
    target = _target_size(requested_size)
    if not target:
        return image_data
    started = time.monotonic()
    deadline = min(started + _TOTAL_SECONDS, deadline_monotonic - _RETURN_RESERVE_SECONDS) if deadline_monotonic else started + _TOTAL_SECONDS
    engine, fit = config.image_upscale_engine, config.image_upscale_fit
    info: dict[str, object] = {
        "configured_engine": engine, "fit": fit,
        "target_size": list(target), "source_bytes": len(image_data),
        "queue_ms": 0, "processing_ms": 0,
    }

    def finish(status: str, reason: str, result: bytes = image_data) -> bytes:
        info.update(status=status, reason=reason, total_ms=round((time.monotonic() - started) * 1000), result_bytes=len(result))
        if report is not None:
            report.update(info)
        log = logger.info if status == "done" or reason == "already_sufficient" else logger.warning
        log({"event": "image_upscale_" + status, "call_id": call_id or "", **info})
        return result

    if len(image_data) > _MAX_INPUT_BYTES:
        return finish("skipped", "input_byte_limit")
    if target[0] * target[1] > _MAX_PIXELS:
        return finish("skipped", "target_pixel_limit")
    if time.monotonic() >= deadline:
        return finish("skipped", "deadline_exhausted")
    try:
        source, animated = _inspect_image(image_data)
    except Exception as exc:
        return finish("skipped", str(exc) if isinstance(exc, _UpscaleError) else "invalid_source")
    info["source_size"] = list(source)
    info["output_size"] = list(source)
    if animated:
        return finish("skipped", "animated_source")
    if source[0] >= target[0] and source[1] >= target[1]:
        return finish("skipped", "already_sufficient")
    queued = time.monotonic()
    acquired = _UPSCALE_SLOTS.acquire(timeout=max(0.0, min(_QUEUE_SECONDS, deadline - queued)))
    info["queue_ms"] = round((time.monotonic() - queued) * 1000)
    if not acquired:
        return finish("skipped", "deadline_exhausted" if time.monotonic() >= deadline else "queue_busy")
    processing = time.monotonic()
    try:
        try:
            result = _render(engine, image_data, target, fit, deadline)
        except Exception as exc:
            reason = "processing_timeout" if isinstance(exc, subprocess.TimeoutExpired) else str(exc) if isinstance(exc, _UpscaleError) else "engine_failed"
            if engine != "sharp_lanczos3" or reason == "processing_timeout" or time.monotonic() >= deadline:
                raise _UpscaleError(reason) from None
            info["fallback_reason"] = reason
            engine = "pillow_lanczos"
            result = _render(engine, image_data, target, fit, deadline)
        info.update(engine=engine, output_size=list(target))
        status, reason = "done", "enlarged"
    except Exception as exc:
        result = image_data
        info["engine"] = engine
        status = "failed"
        reason = "processing_timeout" if isinstance(exc, subprocess.TimeoutExpired) else str(exc) if isinstance(exc, _UpscaleError) else "engine_failed"
    finally:
        info["processing_ms"] = round((time.monotonic() - processing) * 1000)
        _UPSCALE_SLOTS.release()
    return finish(status, reason, result)
