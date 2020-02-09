from typing import Callable

from reportlab.pdfgen.canvas import Canvas

from .dimensions import mm_to_points, Point, Size

MarkerFunction = Callable[[Canvas, Point[float], Size[float], int], None]


def marker_none(
    canvas: Canvas, position: Point[float], size: Size[float], repititions: int
):
    pass


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


MARKERS = {
    "- keine -": marker_none,
    "Spirale": marker_spiral,
    "Diamant": marker_diamond,
}

MARKER_SETS = {
    "- keine -": " ",
    "Großbuchstaben": "ABCDEFGHKMNOPQRSTUVWXYZ",
    "Kleinbuchstaben": "abcdefghkmnopqrstuvwxyz",
    "Zahlen": [str(x) for x in range(1, 26)],
}
