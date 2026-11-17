"""Writes the PWA icons in src/srs/static/icons (plain zlib PNGs, so no imaging dependency)."""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).parent.parent / "src" / "srs" / "static" / "icons"
BG = (79, 70, 229)
CARD = (255, 255, 255)
BACK_CARD = (165, 160, 245)


def _inside_rounded(x: float, y: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _pixel(u: float, v: float, maskable: bool) -> tuple[int, int, int, int]:
    """u, v in [0, 1). Two stacked cards on a rounded square (full-bleed square for maskable icons)."""
    if not maskable and not _inside_rounded(u, v, 0, 0, 1, 1, 0.22):
        return (0, 0, 0, 0)
    s = 0.8 if maskable else 1.0  # keep the motif inside the maskable safe zone
    x, y = (u - 0.5) / s + 0.5, (v - 0.5) / s + 0.5
    if _inside_rounded(x, y, 0.3, 0.2, 0.82, 0.66, 0.06):
        return (*CARD, 255)
    if _inside_rounded(x, y, 0.18, 0.34, 0.7, 0.8, 0.06):
        return (*BACK_CARD, 255)
    return (*BG, 255)


def _png(size: int, maskable: bool) -> bytes:
    raw = b"".join(
        b"\x00" + b"".join(bytes(_pixel((i + 0.5) / size, (j + 0.5) / size, maskable)) for i in range(size))
        for j in range(size)
    )

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "icon-192.png").write_bytes(_png(192, maskable=False))
    (OUT / "icon-512.png").write_bytes(_png(512, maskable=False))
    (OUT / "icon-maskable-512.png").write_bytes(_png(512, maskable=True))


if __name__ == "__main__":
    main()
