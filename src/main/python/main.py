import sys
from pathlib import Path
from typing import Iterable
from io import BytesIO

from fbs_runtime.application_context.PyQt5 import ApplicationContext
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QGroupBox,
    QFileDialog,
    QListWidgetItem,
    QLineEdit,
    QSpinBox,
    QGridLayout,
    QLabel,
    QCheckBox,
    QComboBox,
    QFontComboBox,
    QSlider,
    QScrollArea,
    QSpacerItem,
    QMainWindow,
    QDockWidget,
    QAction
)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QPixmap, QIcon
from PIL.ImageQt import toqpixmap
import pdf2image
from PyPDF2 import PdfFileReader

from lib.dimensions import PAGE_SIZES, Defaults
from lib.underlay import MARKERS, MARKER_SETS
from lib.posterize import posterize_pdf, save_output


class FileList(QListWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)
        self.paths = []

    def mimeTypes(self):
        mimetypes = super().mimeTypes()
        mimetypes.append("text/plain")
        return mimetypes

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
            for url in event.mimeData().urls():
                self.addItem(url.path())
        else:
            event.ignore()

    def addItem(self, item: str):
        file_path = Path(item)
        self.paths.append(file_path)
        super().addItem(file_path.name)

    def takeItem(self, index: int):
        path = self.paths.pop(index)
        super().takeItem(index)
        return path


class InputFilesWidget(QGroupBox):
    def __init__(self, title: str, *args, **kwargs):
        super().__init__(title, *args, **kwargs)

        delete_button = QPushButton(
            QIcon("src/main/icons/actions/delete_file.png"), "", self
        )
        delete_button.setEnabled(False)

        self.file_list = FileList(self)
        self.file_list.itemSelectionChanged.connect(
            lambda: delete_button.setEnabled(True)
        )

        @pyqtSlot()
        def on_remove_selected_item():
            self.file_list.takeItem(self.file_list.currentRow())
            if len(self.file_list.paths) == 0:
                delete_button.setEnabled(False)

        delete_button.clicked.connect(on_remove_selected_item)

        add_button = QPushButton(QIcon("src/main/icons/actions/add_file.png"), "", self)
        add_button.clicked.connect(lambda: self.openFileChooser())

        buttons = QWidget(self)
        buttons_layout = QHBoxLayout()
        buttons.setLayout(buttons_layout)
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(delete_button)

        layout = QVBoxLayout()
        layout.addWidget(self.file_list)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def openFileChooser(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Schnittmusterdateien aussuchen", "", "PDF Dateien (*.pdf)"
        )
        for path in files:
            self.file_list.addItem(path)


class OutputFormatWidget(QGroupBox):
    def __init__(self, title: str, available_formats: Iterable[str], *args, **kwargs):
        super().__init__(title, *args, **kwargs)

        self.outputformats_list = QListWidget(self)

        for format_name in available_formats:
            item = QListWidgetItem(format_name, self.outputformats_list)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # item.setFlags(item.flags() ^ Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked)
            self.outputformats_list.addItem(item)

        layout = QVBoxLayout()
        layout.addWidget(self.outputformats_list)

        self.setLayout(layout)


class OutputFolderWidget(QGroupBox):
    def __init__(self, title: str, *args, **kwargs):
        super().__init__(title, *args, **kwargs)

        self.browse_text = QLineEdit(self)

        browse_button = QPushButton("Auswählen", self)
        browse_button.clicked.connect(lambda: self.openFolderChooser())

        layout = QHBoxLayout()
        layout.addWidget(self.browse_text)
        layout.addWidget(browse_button)

        self.setLayout(layout)

    def openFolderChooser(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Ausgabeordner wählen", self.browse_text.text()
        )
        if folder:
            self.browse_text.setText(folder)


class UnderlaySettingsWidget(QGroupBox):
    def __init__(self, title: str, *args, **kwargs):
        super().__init__(title, *args, **kwargs)
        layout = QGridLayout()
        self.setLayout(layout)

        self.dpi = QSpinBox(self)
        self.dpi.setMaximum(600)
        self.dpi.setMinimum(18)
        self.dpi.setValue(Defaults.DPI)
        layout.addWidget(QLabel("Dokument DPI"), 0, 0)
        layout.addWidget(self.dpi, 0, 1)

        self.overlap = QSpinBox(self)
        self.overlap.setMinimum(0)
        self.overlap.setValue(Defaults.OVERLAP)
        layout.addWidget(QLabel("Überlagerung"), 1, 0)
        layout.addWidget(self.overlap, 1, 1)

        self.multipage = QCheckBox(self)
        layout.addWidget(QLabel("mehrere Seiten"), 2, 0)
        layout.addWidget(self.multipage, 2, 1)


class GlueMarkWidget(QGroupBox):
    def __init__(self, title: str, *args, **kwargs):

        super().__init__(title, *args, **kwargs)
        layout = QGridLayout()
        self.setLayout(layout)

        self.font_size = QSpinBox(self)
        self.font_size.setMinimum(5)
        self.font_size.setMaximum(100)
        self.font_size.setValue(Defaults.FONT_SIZE)
        self.font = QFontComboBox(self)

        layout.addWidget(QLabel("Schrift", self), 0, 0)
        layout.addWidget(self.font_size, 0, 2)
        layout.addWidget(self.font, 0, 1)

        layout.addWidget(QLabel("Marker", self), 4, 0)
        self.marker_type_x = QComboBox(self)
        self.marker_type_x.addItems(MARKERS.keys())
        layout.addWidget(self.marker_type_x, 4, 1)
        self.marker_type_y = QComboBox(self)
        self.marker_type_y.addItems(MARKERS.keys())
        layout.addWidget(self.marker_type_y, 4, 2)

        layout.addWidget(QLabel("Beschriftungen", self), 5, 0)
        self.marker_labels_x = QComboBox(self)
        self.marker_labels_x.addItems(MARKER_SETS.keys())
        layout.addWidget(self.marker_labels_x, 5, 1)
        self.marker_labels_y = QComboBox(self)
        self.marker_labels_y.addItems(MARKER_SETS.keys())
        layout.addWidget(self.marker_labels_y, 5, 2)

        layout.addWidget(QLabel("Größe innen", self), 6, 0)
        self.marker_inner_size = QSlider(Qt.Horizontal, self)
        self.marker_inner_size.setMinimum(10)
        self.marker_inner_size.setMaximum(240)
        self.marker_inner_size.valueChanged.connect(self.validate_outer_size)
        marker_inner_size_label = QLabel(self)
        self.marker_inner_size.valueChanged.connect(
            lambda x: marker_inner_size_label.setText(f"{x} pt")
        )
        layout.addWidget(self.marker_inner_size, 6, 1)
        layout.addWidget(marker_inner_size_label, 6, 2)

        layout.addWidget(QLabel("Größe außen", self), 7, 0)
        self.marker_outer_size = QSlider(Qt.Horizontal, self)
        self.marker_outer_size.setMinimum(15)
        self.marker_outer_size.setMaximum(250)
        self.marker_outer_size.valueChanged.connect(self.validate_inner_size)
        marker_outer_size_label = QLabel(self)
        self.marker_outer_size.valueChanged.connect(
            lambda x: marker_outer_size_label.setText(f"{x} pt")
        )
        layout.addWidget(self.marker_outer_size, 7, 1)
        layout.addWidget(marker_outer_size_label, 7, 2)

        self.marker_inner_size.setValue(35)
        self.marker_outer_size.setValue(45)

    def update_widget_state(self):
        for widget in [
            self.marker_type_x,
            self.marker_type_y,
            self.marker_labels_x,
            self.marker_labels_y,
            self.marker_inner_size,
            self.marker_outer_size,
        ]:
            widget.setEnabled(self.marker_enabled.isChecked())

    def validate_inner_size(self):
        inner_size = self.marker_inner_size.value()
        outer_size = self.marker_outer_size.value()
        if inner_size >= outer_size - 5:
            self.marker_inner_size.setValue(outer_size - 5)

    def validate_outer_size(self):
        inner_size = self.marker_inner_size.value()
        outer_size = self.marker_outer_size.value()
        if outer_size <= inner_size + 5:
            self.marker_outer_size.setValue(inner_size + 5)


class PreviewWidget(QGroupBox):
    def __init__(self, title: str, *args, **kwargs):
        self.current_page = 1
        self.dpi = 40

        super().__init__(title, *args, **kwargs)
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.preview_box = QLabel(self)

        scroller = QScrollArea(self)
        scroller.setWidget(self.preview_box)
        layout.addWidget(scroller)

        control_layout = QHBoxLayout()
        self.button_zoom_fit = QPushButton(
            QIcon("src/main/icons/actions/zoom_fit.png"), "", self
        )
        self.button_zoom_fit.clicked.connect(self.zoom_fit)
        self.button_zoom_out = QPushButton(
            QIcon("src/main/icons/actions/zoom_out.png"), "", self
        )
        self.button_zoom_out.clicked.connect(lambda: self.set_dpi(self.dpi - 10))
        self.button_zoom_in = QPushButton(
            QIcon("src/main/icons/actions/zoom_in.png"), "", self
        )
        self.button_zoom_in.clicked.connect(lambda: self.set_dpi(self.dpi + 10))
        control_layout.addWidget(self.button_zoom_fit)
        control_layout.addWidget(self.button_zoom_out)
        control_layout.addWidget(self.button_zoom_in)

        control_layout.addSpacing(100)

        self.button_prev_page = QPushButton(
            QIcon("src/main/icons/actions/prev.png"), "", self
        )
        self.button_prev_page.clicked.connect(
            lambda: self.set_page(self.current_page - 1)
        )

        self.label_current_page = QLabel("", self)
        self.label_current_page.setAlignment(Qt.AlignCenter)

        self.button_next_page = QPushButton(
            QIcon("src/main/icons/actions/next.png"), "", self
        )
        self.button_next_page.clicked.connect(
            lambda: self.set_page(self.current_page + 1)
        )

        control_layout.addWidget(self.button_prev_page)
        control_layout.addWidget(self.label_current_page)
        control_layout.addWidget(self.button_next_page)

        control_widget = QWidget(self)
        control_widget.setLayout(control_layout)

        layout.addWidget(control_widget)

    def update_preview(self):
        pdf_file = self.pages[self.current_page]
        pdf_file.seek(0)

        preview_image = pdf2image.convert_from_bytes(
            pdf_file.read(), dpi=self.dpi, first_page=0, last_page=0, use_cropbox=True
        )
        image = toqpixmap(preview_image[0])
        self.preview_box.setPixmap(image)
        self.preview_box.resize(image.size())

    def update_controls(self):
        if self.pages:
            num_pages = max(self.pages.keys())
            if self.current_page >= num_pages:
                self.current_page = num_pages

            self.label_current_page.setText(f"{self.current_page} / {num_pages}")
            self.button_prev_page.setEnabled(self.current_page != 1)
            self.button_next_page.setEnabled(self.current_page != num_pages)

    def set_preview_pages(self, pages):
        self.pages = pages
        self.update_preview()
        self.update_controls()

    def set_page(self, page):
        self.current_page = page
        self.update_preview()
        self.update_controls()

    def set_dpi(self, dpi):
        self.dpi = dpi
        self.update_preview()
        self.update_controls()

    def zoom_fit(self):
        width_ratio = self.preview_box.size().width() / self.size().width()
        height_ratio = self.preview_box.size().height() / self.size().height()
        new_dpi = self.dpi / max(width_ratio, height_ratio)
        self.set_dpi(new_dpi)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('Schnitt Tisch')
        self.init_menu()

        self.file_box = InputFilesWidget("Eingabedateien", self)
        self.outputformat_box = OutputFormatWidget(
            "Ausgabeformate", PAGE_SIZES.keys(), self
        )

        io_layout = QVBoxLayout()
        io_layout.addWidget(self.file_box, 3)
        io_layout.addWidget(self.outputformat_box, 1)
        io_widget = QWidget(self)
        io_widget.setMinimumWidth(250)
        io_widget.setMaximumWidth(400)
        io_widget.setLayout(io_layout)

        self.outputfolder_box = OutputFolderWidget("Ausgabepfad", self)
        self.underlaysettings_box = UnderlaySettingsWidget(
            "Dokumenteinstellungen", self
        )
        self.gluemarks_box = GlueMarkWidget("Klebehilfen", self)
        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self.outputfolder_box, 1)
        settings_layout.addWidget(self.underlaysettings_box, 3)
        settings_layout.addWidget(self.gluemarks_box, 5)

        settings_widget = QWidget(self)
        settings_widget.setLayout(settings_layout)
        settings_widget.setMaximumWidth(400)
        settings_widget.setMinimumWidth(350)

        self.preview_widget = PreviewWidget("Vorschau", self)

        reader = PdfFileReader(
            open(
                "/Users/daniel/Documents/pdfposterize/5.1.2020. MisterChilloverA0.pdf",
                "rb",
            )
        )
        page = reader.pages[0]
        output_pages = posterize_pdf(
            page, PAGE_SIZES["A4"], Defaults.OVERLAP, Defaults.DPI
        )
        self.preview_widget.set_preview_pages(output_pages)

        action_button_layout = QHBoxLayout()

        site_link = QLabel('<a href="https://naehcram.de/">by Nähcram</a>')
        site_link.setTextFormat(Qt.RichText)
        site_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        site_link.setOpenExternalLinks(True)
        action_button_layout.addWidget(site_link, alignment=Qt.AlignLeft)

        self.export_button = QPushButton(
            QIcon("src/main/icons/actions/save.png"), "Exportieren"
        )
        self.export_button.setFixedWidth(200)
        action_button_layout.addWidget(self.export_button, alignment=Qt.AlignRight)


        self.setCentralWidget(self.preview_widget)
        left_widget = QDockWidget()
        left_widget.setWidget(io_widget)
        left_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)
        left_widget.setTitleBarWidget(QWidget(self))
        right_widget = QDockWidget()
        right_widget.setWidget(settings_widget)
        right_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)
        right_widget.setTitleBarWidget(QWidget(self))
        self.addDockWidget(Qt.LeftDockWidgetArea, left_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, right_widget)

    def init_menu(self):
        exitAct = QAction( ' &asd', self)        
        exitAct.setShortcut('Ctrl+Q')
        exitAct.setStatusTip('Exit application')
        exitAct.triggered.connect(app.quit)

        exitAct = QAction( 'asdasd', self)        
        exitAct.setShortcut('Ctrl+U')
        exitAct.setStatusTip('asd application')
        exitAct.triggered.connect(app.quit)

        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        fileMenu.addAction(exitAct)
        #menubar.setNativeMenuBar(False)

    def init_statusbar(self):
        self.statusBar()

if __name__ == "__main__":

    app = QApplication([])

    main_window = MainWindow()
    main_window.show()

    exit_code = app.exec_()
    sys.exit(exit_code)
