from reportlab.pdfgen.canvas import Canvas
from io import BytesIO
from reportlab.pdfbase.ttfonts import TTFont
from dataclasses import dataclass
from typing import Tuple, Callable, List, Sequence

from reportlab.pdfbase import pdfmetrics
from PyPDF2 import pdf, PdfFileReader

from .dimensions import mm_to_points, Point, Size

MarkerFunction = Callable[[Canvas, "Point[float]", "Size[float]", int], None]


@dataclass
class OverlayDefinition:
    page_count: Point[int]
    page_size: Size[float]
    overlap: float
    dpi: int

    @property
    def overlay_size(self):
        return self.page_size * self.page_count

@dataclass
class GlueMarkConfig:
    font: str
    font_size: int
    marker_x: str
    marker_y: str
    label_x: str
    label_y: str
    inner_size: int
    outer_size: int

    def toJson(self):
        return self.__dict__

    @classmethod
    def fromJson(cls, dict):
        return GlueMarkConfig(**dict)


def marker_spiral(
    canvas: Canvas, position: Point[float], size: Size[float], repititions: int,
):
    p = canvas.beginPath()

    spacing = (size.y - size.x) / repititions
    inner_radius_x = size.x / 1.3
    inner_radius_y = size.x / 2
    p.moveTo(position.x, position.y + inner_radius_y)
    for round in range(repititions):
        multiplier = lambda frac: spacing * (round + float(frac))
        p.curveTo(
            position.x + inner_radius_x + multiplier(0),
            position.y + inner_radius_y + multiplier(0),
            position.x + inner_radius_x + multiplier(0.25),
            position.y - inner_radius_y - multiplier(0.25),
            position.x,
            position.y - inner_radius_y - multiplier(0.5),
        )
        p.curveTo(
            position.x - inner_radius_x - multiplier(0.5),
            position.y - inner_radius_y - multiplier(0.75),
            position.x - inner_radius_x - multiplier(0.75),
            position.y + inner_radius_y + multiplier(1),
            position.x,
            position.y + inner_radius_y + multiplier(1),
        )

    canvas.drawPath(p, stroke=1)


def marker_diamond(
    canvas: Canvas, position: Point[float], size: Size[float], repititions: int,
):
    p = canvas.beginPath()

    spacing = (size.y - size.x) / repititions
    for round in range(repititions):
        offset = size.x + spacing * round
        p.moveTo(position.x, position.y + offset)
        p.lineTo(position.x + offset, position.y)
        p.lineTo(position.x, position.y - offset)
        p.lineTo(position.x - offset, position.y)
        p.lineTo(position.x, position.y + offset)

    canvas.drawPath(p, stroke=1)


MARKERS = {"- keine -": None, "Spirale": marker_spiral, "Diamant": marker_diamond}

MARKER_SETS = {
    "- keine -": None,
    "Großbuchstaben": "ABCDEFGHKMNOPQRSTUVWXYZ",
    "Kleinbuchstaben": "abcdefghkmnopqrstuvwxyz",
    "Zahlen": frozenset([str(x) for x in range(25)]),
}


def grid(canvas: Canvas, overlay: OverlayDefinition):
    for ix in range(1, overlay.page_count.x):
        x_center = mm_to_points(
            ix * (overlay.page_size.x - overlay.overlap) + overlay.overlap / 2,
            overlay.dpi,
        )
        y1, y2 = 0, mm_to_points(overlay.overlay_size.y, overlay.dpi)
        canvas.line(x_center, y1, x_center, y2)

    for iy in range(1, overlay.page_count.y):
        x1, x2 = 0, mm_to_points(overlay.overlay_size.x, overlay.dpi)
        y_center = mm_to_points(
            ((iy * (overlay.page_size.y - overlay.overlap)) + overlay.overlap / 2),
            overlay.dpi,
        )
        canvas.line(x1, y_center, x2, y_center)


def alignment_markers(
    canvas: Canvas,
    overlay: OverlayDefinition,
    marker_x: MarkerFunction,
    marker_y: MarkerFunction,
    marker_size: Size[float],
):
    for ix in range(1, overlay.page_count.x):
        x_outer = mm_to_points(
            ix * (overlay.page_size.x - overlay.overlap) + overlay.overlap / 2,
            overlay.dpi,
        )
        for iy in range(overlay.page_count.y):
            y_center = mm_to_points(
                overlay.overlay_size.y
                - (
                    ((iy - 2) * (overlay.page_size.y - overlay.overlap))
                    + overlay.overlap / 2
                )
                - (overlay.overlay_size.y / 2),
                overlay.dpi,
            )
            marker_x(
                canvas, Point(x_outer, y_center), marker_size, 3,
            )

    for ix in range(overlay.page_count.x):
        x_center = mm_to_points(
            ix * (overlay.page_size.x - overlay.overlap) + overlay.page_size.x / 2,
            overlay.dpi,
        )
        for iy in range(1, overlay.page_count.y):
            y_bottom = mm_to_points(
                (
                    ((iy) * (overlay.page_size.y - overlay.overlap))
                    + overlay.overlap / 2
                ),
                overlay.dpi,
            )
            marker_y(
                canvas, Point(x_center, y_bottom), marker_size, 3,
            )


def sort_markers(
    canvas: Canvas,
    overlay: OverlayDefinition,
    marker_set_x: Sequence[str],
    marker_set_y: Sequence[str],
    font: str,
    font_size: float,
):
    pdfmetrics.registerFont(TTFont(font, font))
    canvas.setFont(font, font_size)
    canvas.setStrokeColorRGB(0.6, 0.6, 0.6)

    for ix in range(1, overlay.page_count.x):
        x_outer = mm_to_points(
            ix * (overlay.page_size.x - overlay.overlap) + overlay.overlap / 2,
            overlay.dpi,
        )
        for iy in range(overlay.page_count.y):
            y_center = mm_to_points(
                overlay.overlay_size.y
                - (
                    ((iy - 2) * (overlay.page_size.y - overlay.overlap))
                    + overlay.overlap / 2
                )
                - (overlay.overlay_size.y / 2),
                overlay.dpi,
            )
            marker_num = ix - 1 + (iy * (overlay.page_count.x - 1))
            marker = marker_set_x[marker_num]
            canvas.drawCentredString(
                x_outer - font_size / 2, y_center - font_size / 2, marker
            )
            canvas.drawCentredString(
                x_outer + font_size / 2, y_center - font_size / 2, marker
            )

    for ix in range(overlay.page_count.x):
        x_center = mm_to_points(
            ix * (overlay.page_size.x - overlay.overlap) + overlay.page_size.x / 2,
            overlay.dpi,
        )
        for iy in range(1, overlay.page_count.y):
            y_bottom = mm_to_points(
                (
                    ((iy) * (overlay.page_size.y - overlay.overlap))
                    + overlay.overlap / 2
                ),
                overlay.dpi,
            )
            marker_num = ix + ((overlay.page_count.y - iy - 1) * overlay.page_count.x)
            marker = marker_set_y[marker_num]
            canvas.drawCentredString(x_center, y_bottom + font_size / 2, marker)
            canvas.drawCentredString(x_center, y_bottom - font_size / 2, marker)


def assembly_guide(overlay_def: OverlayDefinition) -> pdf.PageObject:
    packet = BytesIO()
    canvas = Canvas(packet, pagesize=overlay_def.page_size)

    canvas.setLineWidth(2)

    grid(canvas, overlay_def)
    alignment_markers(canvas, overlay_def, marker_spiral, marker_diamond, Size(35, 50))
    sort_markers(
        canvas,
        overlay_def,
        MARKER_SETS["Großbuchstaben"],
        MARKER_SETS["Kleinbuchstaben"],
        "Montserrat-Regular.ttf",
        25,
    )

    canvas.save()
    packet.seek(0)
    overlay = PdfFileReader(packet)
    return overlay.pages[0]
