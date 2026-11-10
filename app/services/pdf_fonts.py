from itertools import groupby
import hashlib
import re
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.core.config import get_settings


class UnicodeTTFont(TTFont):
    def addObjects(self, doc):
        existing = set(doc.idToObject)
        super().addObjects(doc)
        for key in set(doc.idToObject) - existing:
            if not key.startswith("toUnicodeCMap:"):
                continue
            stream = doc.idToObject[key]
            # PDF CMaps require UTF-16BE surrogate pairs, not five-digit code points.
            stream.content = re.sub(
                r"(<[0-9A-F]{2}>) <([0-9A-F]{5,6})>",
                lambda match: (
                    match[1] + " <"
                    + chr(int(match[2], 16)).encode("utf-16-be").hex().upper()
                    + ">"
                ),
                stream.content,
            )


def register_pdf_fonts() -> list[str]:
    fonts = []
    for index, filename in enumerate(get_settings().pdf_font_paths):
        path = Path(filename)
        if not path.is_file():
            raise ValueError(
                f"Configured PDF font {index + 1} is unavailable. "
                "Install the font or correct PDF_FONT_PATHS."
            )
        name = "CareerPilotUnicode" + hashlib.sha256(
            str(path.resolve()).encode()
        ).hexdigest()[:16]
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeTTFont(name, str(path)))
        fonts.append(name)
    vera = "CareerPilotVera"
    if vera not in pdfmetrics.getRegisteredFontNames():
        path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        pdfmetrics.registerFont(UnicodeTTFont(vera, str(path)))
    return [*fonts, vera]


def render_pdf_lines(lines: list[str], fonts: list[str]) -> list[str]:
    coverage = {
        name: pdfmetrics.getFont(name).face.charToGlyph for name in fonts
    }
    characters = {char for line in lines for char in line}
    selected = {
        char: next(
            (name for name in fonts if ord(char) in coverage[name]), None
        )
        for char in characters
    }
    unsupported = sorted(ord(char) for char, font in selected.items() if font is None)
    if unsupported:
        codes = ", ".join(f"U+{code:04X}" for code in unsupported[:20])
        raise ValueError(
            f"PDF fonts lack glyphs for {codes}"
            f"{' (additional codes omitted)' if len(unsupported) > 20 else ''}. "
            "No document was saved. Configure PDF_FONT_PATHS with fonts covering "
            "these characters; the source CV does not need to be changed."
        )
    return [
        "".join(
            f'<font name="{font}">{escape("".join(group))}</font>'
            for font, group in groupby(line, key=selected.__getitem__)
        )
        for line in lines
    ]
