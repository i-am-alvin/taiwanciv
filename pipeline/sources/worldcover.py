"""ESA WorldCover 2021 land cover, read from a reduced-resolution level of the cloud-optimised GeoTIFFs.

The 10 m tiles are 36000 × 36000 pixels. A Cloud Optimized GeoTIFF also stores overviews (half, quarter, …
resolution). We read only the 1/16 overview (2250 × 2250 per 3° tile, ~148 m pixels) with HTTP range requests:
the TIFF header and directories first, then the nine 1024 × 1024 deflate tiles of that level. Standard library
only (struct + zlib).
"""

from __future__ import annotations

import struct
import zlib

from ..core.source import Source, SourceInfo

BUCKET = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
# 3° tiles named by their south-west corner; these four cover Taiwan, Penghu, Kinmen and Matsu.
TILES = ["N21E117", "N21E120", "N24E117", "N24E120"]
LEVEL = 4  # IFD index: 0 = full 10 m, 4 = 1/16 (2250 px per 3°)
HEADER_BYTES = 65536
WINDOW = (117.8, 21.6, 122.4, 26.6)  # lon0, lat0, lon1, lat1 kept in the interim

# WorldCover class code → one character, so the interim stores each raster row as a string.
LEGEND = {0: ".", 10: "t", 20: "s", 30: "g", 40: "c", 50: "b", 60: "r", 70: "i", 80: "w", 90: "f", 95: "v", 100: "m"}
CLASSES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up", 60: "Bare / sparse vegetation",
    70: "Snow and ice", 80: "Permanent water bodies", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen",
}


def url(tile: str) -> str:
    return f"{BUCKET}/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"


def read_ifds(head: bytes) -> list[dict]:
    """Directories of a little-endian classic TIFF, as {tag: value or list}."""
    if head[:4] != b"II*\x00":
        raise ValueError("not a little-endian classic TIFF")
    sizes = {1: 1, 2: 1, 3: 2, 4: 4, 16: 8}
    fmt = {1: "B", 2: "c", 3: "H", 4: "I", 16: "Q"}
    off = struct.unpack_from("<I", head, 4)[0]
    out = []
    while off:
        if off + 2 > len(head):
            raise ValueError("TIFF directory beyond the downloaded header; raise HEADER_BYTES")
        n = struct.unpack_from("<H", head, off)[0]
        tags = {}
        for k in range(n):
            tag, typ, cnt = struct.unpack_from("<HHI", head, off + 2 + 12 * k)
            size = sizes.get(typ, 1) * cnt
            pos = off + 2 + 12 * k + 8 if size <= 4 else struct.unpack_from("<I", head, off + 2 + 12 * k + 8)[0]
            if typ in fmt and pos + size <= len(head):
                vals = struct.unpack_from(f"<{cnt}{fmt[typ]}", head, pos)
                tags[tag] = vals[0] if cnt == 1 else list(vals)
        out.append(tags)
        off = struct.unpack_from("<I", head, off + 2 + 12 * n)[0]
    return out


class WorldCover(Source):
    info = SourceInfo(
        id="worldcover",
        title="ESA WorldCover 10 m 2021 v200",
        publisher="European Space Agency (ESA WorldCover consortium); hosted on the AWS Open Data Registry",
        homepage="https://esa-worldcover.org/en",
        license="CC BY 4.0. © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) "
        "processed by ESA WorldCover consortium",
        description="Global land cover from Sentinel-1 and Sentinel-2 at 10 m, read here from the 1/16 overview "
        "of the cloud-optimised GeoTIFFs (~148 m pixels). Each hex's biome (forest, farmland, grassland, wetland, "
        "built-up…) and its land-cover shares come from about 500 pixels sampled inside it.",
        used_for=["Hex land cover (biomes)", "Forest / cropland / built-up shares of each hex"],
    )

    def _header(self, tile: str, force: bool) -> list[dict]:
        p = self.download(url(tile), f"{tile}_header.bin", force=force,
                          headers={"Range": f"bytes=0-{HEADER_BYTES - 1}"}, expect_binary=True)
        return read_ifds(p.read_bytes())

    def fetch(self, force=False):
        for tile in TILES:
            ifd = self._header(tile, force)[LEVEL]
            offs, counts = ifd[324], ifd[325]
            offs = offs if isinstance(offs, list) else [offs]
            counts = counts if isinstance(counts, list) else [counts]
            for k, (o, n) in enumerate(zip(offs, counts)):
                self.download(url(tile), f"{tile}_L{LEVEL}_t{k}.bin", force=force,
                              headers={"Range": f"bytes={o}-{o + n - 1}"}, expect_binary=True)

    def process(self):
        lon0, lat0, lon1, lat1 = WINDOW
        px, size = 0.0, 0
        files = []
        mosaic: dict[tuple[int, int], bytes] = {}  # (tile row from north, tile col) → full-level raster rows
        for tile in TILES:
            ifds = read_ifds((self.raw_dir / f"{tile}_header.bin").read_bytes())
            files.append(f"{tile}_header.bin")
            ifd = ifds[LEVEL]
            w, h, tw, th = ifd[256], ifd[257], ifd[322], ifd[323]
            if ifd.get(259) != 8 or ifd.get(258) != 8:
                raise ValueError(f"{tile}: expected 8-bit deflate tiles, got compression {ifd.get(259)}")
            px = 3.0 / w
            across = -(-w // tw)
            buf = bytearray(w * h)
            n_tiles = len(ifd[324]) if isinstance(ifd[324], list) else 1
            for k in range(n_tiles):
                name = f"{tile}_L{LEVEL}_t{k}.bin"
                files.append(name)
                data = zlib.decompress((self.raw_dir / name).read_bytes())
                ty, tx = divmod(k, across)
                for r in range(th):
                    y = ty * th + r
                    if y >= h:
                        break
                    x0 = tx * tw
                    n = min(tw, w - x0)
                    buf[y * w + x0: y * w + x0 + n] = data[r * tw: r * tw + n]
            south, west = int(tile[1:3]), int(tile[4:7])
            mosaic[(south, west)] = bytes(buf)
            size = w
        # Crop the window out of the 2x2 mosaic of 3° tiles: rows north → south, columns west → east.
        nrow = round((lat1 - lat0) / px)
        ncol = round((lon1 - lon0) / px)
        rows = []
        for r in range(nrow):
            lat = lat1 - (r + 0.5) * px
            south = 24 if lat >= 24 else 21
            ty = int((south + 3 - lat) / px)
            line = []
            for c in range(ncol):
                lon = lon0 + (c + 0.5) * px
                west = 120 if lon >= 120 else 117
                tx = int((lon - west) / px)
                code = mosaic[(south, west)][min(ty, size - 1) * size + min(tx, size - 1)]
                line.append(LEGEND.get(code, "."))
            rows.append("".join(line))
        return {
            "vintage": "ESA WorldCover 2021 v200, 1/16 overview (~148 m)",
            "_files": files,
            "crs": "EPSG:4326",
            # Pixel centre of column 0 / row 0 and pixel size in degrees (rows go south).
            "lon0": lon0 + px / 2, "lat0": lat1 - px / 2, "px": px,
            "cols": ncol, "rows": rows,
            "legend": {ch: code for code, ch in LEGEND.items()},
            "classes": CLASSES,
        }
