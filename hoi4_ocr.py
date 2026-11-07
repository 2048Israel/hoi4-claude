"""Read text off the HOI4 window with the OCR engine built into Windows (Windows.Media.Ocr).

Used by hoi4_actions.py to verify clicks and to read lists, so the player gets words instead of screenshots.

    from hoi4_ocr import ocr_image
    for line in ocr_image(pil_image, origin=(x0, y0), upscale=2):
        print(line.text, line.box)   # box is in game-window pixels: (x0, y0, x1, y1)
"""
import asyncio
import io
from dataclasses import dataclass


@dataclass
class OcrLine:
    text: str
    box: tuple  # (x0, y0, x1, y1) in game-window pixels

    @property
    def center(self):
        return ((self.box[0] + self.box[2]) // 2, (self.box[1] + self.box[3]) // 2)


_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
        _ENGINE = OcrEngine.try_create_from_language(Language("en-US"))
        if _ENGINE is None:
            raise RuntimeError("Windows OCR has no English (en-US) language pack")
    return _ENGINE


async def _recognize(png):
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    return await _engine().recognize_async(bitmap)


def ocr_image(img, origin=(0, 0), upscale=2):
    """OCR a PIL image cropped from the game window at `origin`. Returns OcrLine list, top to bottom.
    Upscaling helps with the game's small fonts."""
    from PIL import Image
    if upscale != 1:
        img = img.resize((img.width * upscale, img.height * upscale), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    result = asyncio.run(_recognize(buf.getvalue()))
    ox, oy = origin
    lines = []
    for line in result.lines:
        rects = [w.bounding_rect for w in line.words]
        if not rects:
            continue
        x0 = min(r.x for r in rects) / upscale + ox
        y0 = min(r.y for r in rects) / upscale + oy
        x1 = max(r.x + r.width for r in rects) / upscale + ox
        y1 = max(r.y + r.height for r in rects) / upscale + oy
        lines.append(OcrLine(line.text, (int(x0), int(y0), int(x1), int(y1))))
    lines.sort(key=lambda l: (l.box[1], l.box[0]))
    return lines
