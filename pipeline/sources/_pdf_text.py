"""A small PDF text reader (standard library only): the positioned text runs of each page.

Enough for a typeset statistical report whose tables are text (one text object per cell): it reads the objects of
a PDF (object streams included), walks the page tree, decodes each page's content stream and maps character codes
to Unicode with the fonts' own ToUnicode tables. It does not handle encryption, rotated text or fonts without a
ToUnicode table (their codes are read as Latin-1, which is right for the digits of a standard-encoded font).
"""

from __future__ import annotations

import re
import zlib

_OBJ = re.compile(rb"(\d+)\s+0\s+obj\b")
_REF = rb"\s*(\d+)\s+0\s+R"
# one token of a content stream: string, hex string, dictionary or array bracket, name, number, operator, comment
_TOKEN = re.compile(
    rb"(?P<str>\((?:\\.|[^\\()]|\((?:\\.|[^\\()])*\))*\))"
    rb"|<<|>>"
    rb"|(?P<hex><[0-9A-Fa-f\s]*>)"
    rb"|\[|\]"
    rb"|(?P<name>/[^\s/\[\]<>()%]*)"
    rb"|(?P<num>[-+]?(?:\d+\.?\d*|\.\d+))"
    rb"|(?P<op>[A-Za-z'\"*]+)"
    rb"|%[^\r\n]*", re.S)
_ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f", b"(": b"(", b")": b")", b"\\": b"\\"}


def _inflate(raw: bytes) -> bytes:
    try:
        return zlib.decompress(raw)
    except zlib.error:
        return zlib.decompressobj().decompress(raw)


def _literal(tok: bytes) -> bytes:
    """Bytes of a PDF string token: (literal with escapes) or <hex>."""
    if tok.startswith(b"<"):
        h = re.sub(rb"\s", b"", tok[1:-1])
        return bytes.fromhex((h + b"0" if len(h) % 2 else h).decode())
    out, s, i = bytearray(), tok[1:-1], 0
    while i < len(s):
        c = s[i:i + 1]
        if c != b"\\":
            out += c
            i += 1
            continue
        nxt = s[i + 1:i + 2]
        if nxt in _ESC:
            out += _ESC[nxt]
            i += 2
        elif nxt.isdigit():
            m = re.match(rb"[0-7]{1,3}", s[i + 1:])
            out.append(int(m.group(0), 8) & 255)
            i += 1 + len(m.group(0))
        else:
            i += 2 if nxt in (b"\n", b"\r") else 1
    return bytes(out)


class Pdf:
    def __init__(self, data: bytes):
        if b"/Encrypt" in data[-4096:]:
            raise ValueError("encrypted PDF")
        self.objs: dict[int, bytes] = {}
        pos = 0
        while m := _OBJ.search(data, pos):
            num, start = int(m.group(1)), m.end()
            end = data.find(b"endobj", start)
            s = data.find(b"stream", start)
            if 0 <= s < end or (s >= 0 and end < 0):  # a stream object: skip the body by its /Length
                length = re.search(rb"/Length\s+(\d+)(?!\s+0\s+R)", data[start:s])
                body_at = s + 6 + (2 if data[s + 6:s + 8] == b"\r\n" else 1)
                after = body_at + int(length.group(1)) if length else data.find(b"endstream", body_at)
                end = data.find(b"endobj", after)
            if end < 0:
                break
            self.objs[num] = data[start:end]
            pos = end + 6
        for body in list(self.objs.values()):
            if re.search(rb"/Type\s*/ObjStm", body[:400]):
                self._expand(body)
        self._cmaps: dict[int, tuple[int, dict[int, str]]] = {}

    # ---- objects

    def _expand(self, body: bytes) -> None:
        head = body[:body.find(b"stream")]
        n = int(re.search(rb"/N\s+(\d+)", head).group(1))
        first = int(re.search(rb"/First\s+(\d+)", head).group(1))
        s = self.stream(body)
        nums = [int(v) for v in s[:first].split()]
        for i in range(n):
            off = nums[2 * i + 1]
            end = nums[2 * i + 3] if i + 1 < n else len(s) - first
            self.objs.setdefault(nums[2 * i], s[first + off:first + end])

    def stream(self, body: bytes) -> bytes:
        s = body.find(b"stream")
        at = s + 6 + (2 if body[s + 6:s + 8] == b"\r\n" else 1)
        raw = body[at:body.rfind(b"endstream")]
        return _inflate(raw) if b"FlateDecode" in body[:s] else raw

    def _dict_or_ref(self, body: bytes, key: bytes) -> bytes:
        """The dictionary under /key, whether written inline or as a reference."""
        m = re.search(key + _REF, body)
        if m:
            return self.objs.get(int(m.group(1)), b"")
        i = body.find(key)
        return body[i + len(key):] if i >= 0 else b""

    # ---- pages

    def pages(self) -> list[int]:
        root = next(b for b in self.objs.values() if re.search(rb"/Type\s*/Catalog\b", b[:2000]))
        out: list[int] = []

        def walk(num: int) -> None:
            body = self.objs[num]
            head = body[:body.find(b"stream")] if b"stream" in body else body
            if re.search(rb"/Type\s*/Pages\b", head):
                kids = re.search(rb"/Kids\s*\[(.*?)\]", head, re.S)
                for k in re.findall(rb"(\d+)\s+0\s+R", kids.group(1)):
                    walk(int(k))
            else:
                out.append(num)

        walk(int(re.search(rb"/Pages" + _REF, root).group(1)))
        return out

    def _fonts(self, page: bytes) -> dict[bytes, int]:
        res = self._dict_or_ref(page, b"/Resources")
        fonts = self._dict_or_ref(res, b"/Font")
        end = fonts.find(b">>")
        return {name: int(num) for name, num in re.findall(rb"(/[^\s/]+)" + _REF, fonts[:end if end >= 0 else None])}

    def _cmap(self, font_num: int) -> tuple[int, dict[int, str]]:
        """(bytes per code, code → text) from the font's ToUnicode table; (1, {}) if it has none."""
        if font_num in self._cmaps:
            return self._cmaps[font_num]
        font = self.objs.get(font_num, b"")
        width = 2 if re.search(rb"/Subtype\s*/Type0\b", font) else 1
        table: dict[int, str] = {}
        m = re.search(rb"/ToUnicode" + _REF, font)
        if m:
            cmap = self.stream(self.objs[int(m.group(1))])

            def uni(h: bytes) -> str:
                return bytes.fromhex(h.decode()).decode("utf-16-be", "replace")

            for block in re.findall(rb"beginbfchar(.*?)endbfchar", cmap, re.S):
                for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
                    table[int(src, 16)] = uni(dst)
            for block in re.findall(rb"beginbfrange(.*?)endbfrange", cmap, re.S):
                for lo, hi, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[.*?\])", block, re.S):
                    lo, hi = int(lo, 16), int(hi, 16)
                    if dst.startswith(b"["):
                        for k, d in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", dst)):
                            table[lo + k] = uni(d)
                    else:
                        base = int(dst[1:-1], 16)
                        digits = len(dst) - 2
                        for k in range(hi - lo + 1):
                            table[lo + k] = uni(f"{base + k:0{digits}X}".encode())
        self._cmaps[font_num] = (width, table)
        return self._cmaps[font_num]

    def _decode(self, raw: bytes, font_num: int | None) -> str:
        width, table = self._cmap(font_num) if font_num is not None else (1, {})
        if not table:
            return raw.decode("latin-1")
        codes = [int.from_bytes(raw[i:i + width], "big") for i in range(0, len(raw) - width + 1, width)]
        return "".join(table.get(c, "") for c in codes)

    def page_text(self, page_num: int) -> list[tuple[float, float, str]]:
        """(x, y, text) for each text-showing operator of the page, in stream order. x, y are the text line's
        origin in page units (y up); the page's transformation matrix is taken to be the identity."""
        page = self.objs[page_num]
        fonts = self._fonts(page)
        refs = re.search(rb"/Contents\s*\[(.*?)\]", page, re.S)
        nums = re.findall(rb"(\d+)\s+0\s+R", refs.group(1)) if refs else re.findall(rb"/Contents" + _REF, page)
        parts = []
        for n in nums:
            body = self.objs[int(n)]
            if b"stream" in body:
                parts.append(self.stream(body))
            else:  # the reference leads to an array of content streams
                parts += [self.stream(self.objs[int(k)]) for k in re.findall(rb"(\d+)\s+0\s+R", body)]
        content = b"\n".join(parts)
        out = []
        font = None
        a = d = 1.0
        x = y = 0.0
        nums: list[float] = []  # the operands since the last operator
        strs: list[bytes] = []
        names: list[bytes] = []
        for m in _TOKEN.finditer(content):
            kind = m.lastgroup
            if kind == "num":
                nums.append(float(m.group()))
            elif kind in ("str", "hex"):
                strs.append(m.group())
            elif kind == "name":
                names.append(m.group())
            elif kind == "op":
                op = m.group()
                if op == b"Tf" and names:
                    font = fonts.get(names[-1])
                elif op == b"Tm" and len(nums) >= 6:
                    a, _, _, d, x, y = nums[-6:]
                elif op in (b"Td", b"TD") and len(nums) >= 2:
                    x, y = x + nums[-2] * a, y + nums[-1] * d
                elif op == b"BT":
                    a = d = 1.0
                    x = y = 0.0
                elif op in (b"Tj", b"TJ", b"'", b'"') and strs:
                    text = "".join(self._decode(_literal(t), font) for t in strs)
                    if text.strip():
                        out.append((x, y, text))
                nums, strs, names = [], [], []
        return out
