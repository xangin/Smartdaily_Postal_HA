"""Image helpers."""

from __future__ import annotations

import io


def to_jpeg(data: bytes) -> bytes:
    """Convert any Pillow-readable image (WebP/PNG) to JPEG.

    智生活照片是 WebP，多數通知服務（例如 LINE）只收 JPEG/PNG。
    Pillow 是 Home Assistant 核心依賴；在 executor 中呼叫。
    """
    from PIL import Image  # noqa: PLC0415 - 只在需要時載入

    with Image.open(io.BytesIO(data)) as img:
        if img.format == "JPEG":
            return data
        out = io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=90)
        return out.getvalue()
