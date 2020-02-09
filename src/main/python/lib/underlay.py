from reportlab.pdfgen.canvas import Canvas
from io import BytesIO
from reportlab.pdfbase.ttfonts import TTFont
from dataclasses import dataclass
from typing import Tuple, Sequence

from reportlab.pdfbase import pdfmetrics
from PyPDF2 import pdf, PdfFileReader

from .dimensions import mm_to_points, Point, Size
from .markers import MarkerFunction, MARKERS, MARKER_SETS


@dataclass
class UnderlayDefinition:
    page_count: Point[int]
    page_size: Size[float]
    overlap: float
    dpi: int

    @property
    def underlay_size(self):
        return self.page_size * self.page_count


@dataclass
class GlueMarkDefinition:
    font: str = "Arial.ttf"
    font_size: int = 25
    grid_color: Tuple[float, float, float] = (0.7, 0.7, 0.7)
    grid_width: float = 3
    marker_color: Tuple[float, float, float] = (0.7, 0.7, 0.7)
    marker_x: MarkerFunction = list(MARKERS.values())[0]
    marker_y: MarkerFunction = list(MARKERS.values())[0]
    label_x: Sequence[str] = list(MARKER_SETS.values())[0]
    label_y: Sequence[str] = list(MARKER_SETS.values())[0]
    size: Size = Size(35, 50)
    repititions: int = 3


def grid(canvas: Canvas, underlay: UnderlayDefinition, marker: GlueMarkDefinition):

    canvas.setLineWidth(marker.grid_width)
    canvas.setStrokeColor(marker.grid_color)

    for ix in range(1, underlay.page_count.x):
        x_center = mm_to_points(
            ix * (underlay.page_size.x - underlay.overlap) + underlay.overlap / 2,
            underlay.dpi,
        )
        y1, y2 = 0, mm_to_points(underlay.underlay_size.y, underlay.dpi)
        canvas.line(x_center, y1, x_center, y2)

    for iy in range(1, underlay.page_count.y):
        x1, x2 = 0, mm_to_points(underlay.underlay_size.x, underlay.dpi)
        y_center = mm_to_points(
            ((iy * (underlay.page_size.y - underlay.overlap)) + underlay.overlap / 2),
            underlay.dpi,
        )
        canvas.line(x1, y_center, x2, y_center)


def alignment_markers(
    canvas: Canvas, underlay: UnderlayDefinition, marker: GlueMarkDefinition,
):
    canvas.setLineWidth(marker.grid_width)
    canvas.setStrokeColorRGB(*marker.marker_color)
    for ix in range(1, underlay.page_count.x):
        x_outer = mm_to_points(
            ix * (underlay.page_size.x - underlay.overlap) + underlay.overlap / 2,
            underlay.dpi,
        )
        for iy in range(underlay.page_count.y):
            y_center = mm_to_points(
                underlay.underlay_size.y
                - (
                    ((iy - 2) * (underlay.page_size.y - underlay.overlap))
                    + underlay.overlap / 2
                )
                - (underlay.underlay_size.y / 2),
                underlay.dpi,
            )
            marker.marker_x(
                canvas, Point(x_outer, y_center), marker.size, marker.repititions
            )

    for ix in range(underlay.page_count.x):
        x_center = mm_to_points(
            ix * (underlay.page_size.x - underlay.overlap) + underlay.page_size.x / 2,
            underlay.dpi,
        )
        for iy in range(1, underlay.page_count.y):
            y_bottom = mm_to_points(
                (
                    ((iy) * (underlay.page_size.y - underlay.overlap))
                    + underlay.overlap / 2
                ),
                underlay.dpi,
            )
            marker.marker_y(
                canvas, Point(x_center, y_bottom), marker.size, marker.repititions
            )


def sort_markers(
    canvas: Canvas, underlay: UnderlayDefinition, marker: GlueMarkDefinition
):
    pdfmetrics.registerFont(TTFont(marker.font, marker.font))
    canvas.setFont(marker.font, marker.font_size)
    canvas.setStrokeColorRGB(*marker.marker_color)

    for ix in range(1, underlay.page_count.x):
        x_outer = mm_to_points(
            ix * (underlay.page_size.x - underlay.overlap) + underlay.overlap / 2,
            underlay.dpi,
        )
        for iy in range(underlay.page_count.y):
            y_center = mm_to_points(
                underlay.underlay_size.y
                - (
                    ((iy - 2) * (underlay.page_size.y - underlay.overlap))
                    + underlay.overlap / 2
                )
                - (underlay.underlay_size.y / 2),
                underlay.dpi,
            )
            marker_num = ix - 1 + (iy * (underlay.page_count.x - 1))
            marker_label = marker.label_x[marker_num % len(marker.label_x)]
            canvas.drawCentredString(
                x_outer - marker.font_size / 2,
                y_center - marker.font_size / 2,
                marker_label,
            )
            canvas.drawCentredString(
                x_outer + marker.font_size / 2,
                y_center - marker.font_size / 2,
                marker_label,
            )

    for ix in range(underlay.page_count.x):
        x_center = mm_to_points(
            ix * (underlay.page_size.x - underlay.overlap) + underlay.page_size.x / 2,
            underlay.dpi,
        )
        for iy in range(1, underlay.page_count.y):
            y_bottom = mm_to_points(
                (
                    ((iy) * (underlay.page_size.y - underlay.overlap))
                    + underlay.overlap / 2
                ),
                underlay.dpi,
            )
            marker_num = ix + ((underlay.page_count.y - iy - 1) * underlay.page_count.x)
            marker_label = marker.label_y[marker_num % len(marker.label_y)]
            canvas.drawCentredString(
                x_center, y_bottom + marker.font_size / 2, marker_label
            )
            canvas.drawCentredString(
                x_center, y_bottom - marker.font_size / 2, marker_label
            )


def assembly_guide(
    underlay_def: UnderlayDefinition, marker_def: GlueMarkDefinition
) -> pdf.PageObject:
    packet = BytesIO()
    canvas = Canvas(packet, pagesize=underlay_def.page_size)

    grid(canvas, underlay_def, marker_def)
    alignment_markers(canvas, underlay_def, marker_def)

    sort_markers(canvas, underlay_def, marker_def)

    canvas.save()
    packet.seek(0)
    underlay = PdfFileReader(packet)
    return underlay.pages[0]
