from argparse import ArgumentParser
from pathlib import Path
from os import makedirs
from io import BytesIO
import copy
import math

from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from PyPDF2 import PdfFileReader, PdfFileWriter, pdf

IN_TO_MM = 25.4
DEFAULT_DPI = 72
DEFAULT_OVERLAP = 10
PAGE_SIZES = {"A4": (210, 294), "A3": (294, 420)}


def mm_to_points(size, dpi):
    """
    convert units MM to native units (points)
    """
    return (size / IN_TO_MM) * dpi


def mm_to_native(x, y, dpi, page_size):
    """
    convert from x,y coordinates in mm (origin upper left corner)
    to pdf native (points, lower left corner)
    """
    y = page_size[1] - y
    return [(size / IN_TO_MM) * dpi for size in (x, y)]


def spiral(canvas, x, y, inner_diameter, outer_diameter, rounds=4):
    p = canvas.beginPath()

    spacing = (outer_diameter - inner_diameter) / rounds
    inner_radius_x = inner_diameter / 1.3
    inner_radius_y = inner_diameter / 2
    p.moveTo(x, y + inner_radius_y)
    for round in range(rounds):
        multiplier = lambda frac: spacing * (round + float(frac))
        p.curveTo(
            x + inner_radius_x + multiplier(0),
            y + inner_radius_y + multiplier(0),
            x + inner_radius_x + multiplier(0.25),
            y - inner_radius_y - multiplier(0.25),
            x,
            y - inner_radius_y - multiplier(0.5),
        )
        p.curveTo(
            x - inner_radius_x - multiplier(0.5),
            y - inner_radius_y - multiplier(0.75),
            x - inner_radius_x - multiplier(0.75),
            y + inner_radius_y + multiplier(1),
            x,
            y + inner_radius_y + multiplier(1),
        )

    canvas.drawPath(p, stroke=1)


def get_overlay(overlay_size, page_size, overlap, dpi, pages_x, pages_y):
    packet = BytesIO()
    can = Canvas(packet, pagesize=page_size)

    content_size_x, content_size_y = ((x - overlap * 2) for x in page_size)

    font_size = 20
    spiral_size = 35, 75
    can.setLineWidth(2)
    pdfmetrics.registerFont(TTFont("Montserrat", "Montserrat-Regular.ttf"))
    can.setFont("Montserrat", font_size)
    can.setStrokeColorRGB(0.6, 0.6, 0.6)

    for ix in range(1, pages_x):
        x_center = mm_to_points(ix * (page_size[0] - overlap) + overlap / 2, dpi)
        y1, y2 = 0, mm_to_points(overlay_size[1], dpi)
        can.line(x_center, y1, x_center, y2)

    for iy in range(pages_y):
        x1, x2 = 0, mm_to_points(overlay_size[0], dpi)
        y_center = mm_to_points(
            (((iy + 1) * (page_size[1] - overlap)) + overlap / 2), dpi
        )
        can.line(x1, y_center, x2, y_center)

    for ix in range(1, pages_x):
        x_outer = mm_to_points(ix * (page_size[0] - overlap) + overlap / 2, dpi)
        for iy in range(pages_y):
            y_center = mm_to_points(
                overlay_size[1]
                - (((iy - 2) * (page_size[1] - overlap)) + overlap / 2)
                - (overlay_size[1] / 2),
                dpi,
            )
            spiral(
                can,
                x_outer,
                y_center,
                inner_diameter=spiral_size[0],
                outer_diameter=spiral_size[1],
                rounds=3,
            )
            marker = chr(ord("A") + ix - 1 + (iy * (pages_x - 1)))
            can.drawCentredString(
                x_outer - font_size / 2, y_center - font_size / 2, marker
            )
            can.drawCentredString(
                x_outer + font_size / 2, y_center - font_size / 2, marker
            )

    for ix in range(pages_x):
        x_center = mm_to_points(ix * (page_size[0] - overlap) + page_size[0] / 2, dpi)
        for iy in range(1, pages_y):
            y_bottom = mm_to_points(
                (((iy) * (page_size[1] - overlap)) + overlap / 2), dpi
            )
            spiral(
                can,
                x_center,
                y_bottom,
                inner_diameter=spiral_size[0],
                outer_diameter=spiral_size[1],
                rounds=3,
            )
            marker = chr(ord("a") + ix + ((pages_y - iy - 1) * pages_x))
            can.drawCentredString(x_center, y_bottom + font_size / 2, marker)
            can.drawCentredString(x_center, y_bottom - font_size / 2, marker)

    can.save()
    packet.seek(0)
    overlay = PdfFileReader(packet)
    return overlay.pages[0]


if __name__ == "__main__":
    parser = ArgumentParser("pdfposterize", "split a big PDF file into multiple pages")

    parser.add_argument(
        "-i", "--input", required=True, type=Path, help="the file to process"
    )
    parser.add_argument(
        "--dpi", default=DEFAULT_DPI, type=int, help="DPI of the input file"
    )
    parser.add_argument(
        "-f",
        "--page_format",
        choices=PAGE_SIZES.keys(),
        type=str,
        default="A4",
        help="physical format of the pages to generate",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_OVERLAP,
        help="overlap each page in x and y direction [mm]",
    )
    parser.add_argument(
        "--multipage",
        action="store_true",
        default=False,
        help="output a seperate file for each page instead of a single PDF",
    )
    args = parser.parse_args()

    with open(args.input, "rb") as input_stream:
        input = PdfFileReader(input_stream)

        if len(input.pages) > 1:
            raise ValueError("Only single page PDFs allowed")

        # calculate points per mm
        page = input.pages[0]

        input_size = [(float(x) / args.dpi) * IN_TO_MM for x in page.mediaBox[2:]]
        page_size = PAGE_SIZES[args.page_format]
        pages_x, pages_y = (
            int(input_size[x] // (page_size[x] - args.overlap)) + 1 for x in range(2)
        )

        output_size = page_size[0] * pages_x, page_size[1] * pages_y
        output_container = pdf.PageObject.createBlankPage(
            width=mm_to_points(output_size[0], args.dpi),
            height=mm_to_points(output_size[1], args.dpi),
        )

        output_container.mergePage(page)
        output_container.mergePage(
            get_overlay(
                output_size, page_size, args.overlap, args.dpi, pages_x, pages_y
            )
        )

        output_pages = {}

        for ix in range(pages_x):
            for iy in range(pages_y):

                x1, y1 = (
                    max(0, ix * (page_size[0] - args.overlap)),
                    input_size[1] - max(0, iy * (page_size[1] - args.overlap)),
                )

                x2, y2 = (x1 + page_size[0]), (y1 - page_size[1])

                output_container.cropBox.lowerLeft = mm_to_native(
                    x1, y1, args.dpi, input_size
                )
                output_container.cropBox.upperRight = mm_to_native(
                    x2, y2, args.dpi, input_size
                )

                page_num = ix + ((pages_y - iy - 1) * pages_x) + 1

                page_file_writer = PdfFileWriter()
                page_file_writer.addPage(output_container)
                page_file = BytesIO()
                page_file_writer.write(page_file)
                page_file.seek(0)

                output_pages[page_num] = page_file

        if args.multipage:
            output_folder = args.input.parent.joinpath(args.input.stem)
            makedirs(output_folder, exist_ok=True)

            for page_num, page in output_pages.items():
                filename = (
                    f"{args.input.stem}_{args.page_format}_page{page_num:03d}.pdf"
                )
                filepath = output_folder.joinpath(filename)

                with open(filepath, "wb") as output_stream:
                    output_stream.write(page.read())
        else:
            filename = f"{args.input.stem}_{args.page_format}.pdf"
            filepath = args.input.parent.joinpath(filename)

            file_writer = PdfFileWriter()

            for _, page in sorted(output_pages.items(), key=lambda kv: kv[0]):
                page_reader = PdfFileReader(page)
                file_writer.addPage(page_reader.pages[0])

            with open(filepath, "wb") as output_stream:
                file_writer.write(output_stream)
