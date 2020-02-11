from io import BytesIO
import copy
import os
from typing import MutableMapping, Sequence
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.ttfonts import TTFont

from PyPDF2 import PdfFileReader, PdfFileWriter, pdf

from .underlay import assembly_guide, UnderlayDefinition, Point, GlueMarkDefinition
from .dimensions import mm_to_points, points_to_mm


def posterize_pdf(
    in_file: Path,
    page_size: Point[float],
    overlap: float,
    dpi: int,
    marker_def: GlueMarkDefinition,
) -> Sequence[BytesIO]:


    reader = PdfFileReader(open(in_file, "rb",))

    print(in_file)
    page = reader.pages[0]
    
    input_size = Point(
        points_to_mm(float(page.mediaBox[2]), dpi),
        points_to_mm(float(page.mediaBox[3]), dpi),
    )
    page_count = ((input_size // (page_size - overlap)) + 1).as_integer()
    output_size = page_size * page_count

    output_container = pdf.PageObject.createBlankPage(
        width=mm_to_points(output_size.x, dpi), height=mm_to_points(output_size.y, dpi),
    )

    underlay_def = UnderlayDefinition(page_count, page_size, overlap, dpi)
    output_container.mergePage(assembly_guide(underlay_def, marker_def))
    output_container.mergePage(page)

    output_pages: MutableMapping[int, pdf.PageObject] = {}

    for ix in range(page_count.x):
        for iy in range(page_count.y):

            x1, y1 = (
                max(0, ix * (page_size.x - overlap)),
                input_size.y - max(0, iy * (page_size.y - overlap)),
            )

            x2, y2 = x1 + page_size.x, y1 - page_size.y

            output_container.cropBox.lowerLeft = (
                mm_to_points(x1, dpi),
                mm_to_points(input_size.y - y1, dpi),
            )

            output_container.cropBox.upperRight = (
                mm_to_points(x2, dpi),
                mm_to_points(input_size.y - y2, dpi),
            )

            page_num = ix + ((page_count.y - iy - 1) * page_count.x) + 1

            page_file_writer = PdfFileWriter()
            page_file_writer.addPage(output_container)
            page_file = BytesIO()
            page_file_writer.write(page_file)
            page_file.seek(0)

            output_pages[page_num] = page_file
    return [output_pages[key] for key in sorted(output_pages.keys())]


def save_output(files: Sequence[Path], pages: Sequence[BytesIO]):
    multipage = len(files) > 1 and len(files) == len(pages)

    if multipage:
        os.makedirs(files[0].parent, exist_ok=True)
        for filepath, page in zip(files, pages):
            with open(filepath, "wb") as output_stream:
                output_stream.write(page.read())
    else:
        file_writer = PdfFileWriter()

        for page in pages:
            page_reader = PdfFileReader(page)
            file_writer.addPage(page_reader.pages[0])

        with open(files[0], "wb") as output_stream:
            file_writer.write(output_stream)

def get_save_paths(output_location: Path, filename: Path, multipage: bool, pages: Sequence[BytesIO]):

    if multipage:
        paths = []
        for page_num, page in enumerate(pages):
            filepath = output_location.joinpath(filename, f"page{page_num + 1:03d}.pdf")
            paths.append(filepath)
        return paths
    else:
        return [output_location.joinpath(f"{filename}.pdf")]
