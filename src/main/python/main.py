from argparse import ArgumentParser
from pathlib import Path
from os import makedirs

from PyPDF2 import PdfFileReader, PdfFileWriter, pdf

from lib.dimensions import DEFAULT_DPI, PAGE_SIZES, DEFAULT_OVERLAP
from lib.posterize import posterize_pdf, save_output, get_save_paths

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
        page_size = PAGE_SIZES[args.page_format]

        output_location = args.input.parent.joinpath()

        output_pages = posterize_pdf(page, page_size, args.overlap, args.dpi)
        output_files = get_save_paths(
            args.input.parent,
            f"{args.input.stem}_{args.page_format}",
            args.multipage,
            output_pages,
        )
        save_output(output_files, output_pages)
