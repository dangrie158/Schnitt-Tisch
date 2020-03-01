import sys
import os
from pathlib import Path
from typing import Iterable, Sequence, Optional
from threading import Thread
from io import BytesIO
from dataclasses import dataclass, field

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
    QSlider,
    QScrollArea,
    QSpacerItem,
    QMainWindow,
    QDockWidget,
    QAction,
    QMessageBox,
    QListWidgetItem,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSlot, QSize, QSettings
from PyQt5.QtGui import QPixmap, QIcon, QMovie
from PIL.ImageQt import toqpixmap
from fitz import Document, Matrix
from PyPDF2 import PdfFileReader

from lib.dimensions import PAGE_SIZES, Defaults, Size
from lib.underlay import MARKERS, MARKER_SETS, GlueMarkDefinition, UnderlayDefinition
from lib.posterize import posterize_pdf, save_output, get_save_paths
from lib.fonts import font_manager

VERSION = "0.1.2"


@dataclass
class GuiSettings:
    input_files: Sequence[str] = field(default_factory=list)
    output_formats: Sequence[str] = field(default_factory=list)


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
                if not self.addItem(url.path()):
                    break
        else:
            event.ignore()

    def addItem(self, item: str):
        file_path = Path(item)
        if file_path.suffix == ".pdf":
            self.paths.append(file_path)
            new_item = QListWidgetItem(
                QIcon(appctxt.get_resource("files/pdf.png")), file_path.name, self
            )
            super().addItem(new_item)
            self.setCurrentItem(new_item)
            return True
        else:
            QMessageBox.information(self, "Fehler", "Nur PDF Dateien erlaubt")
            return False

    def takeItem(self, index: int):
        path = self.paths.pop(index)
        super().takeItem(index)
        return path


class InputFilesWidget(QGroupBox):
    def __init__(self, title: str, *args, **kwargs):
        super().__init__(title, *args, **kwargs)

        delete_button = QPushButton(
            QIcon(appctxt.get_resource("actions/delete_file.png")), "", self
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

        add_button = QPushButton(
            QIcon(appctxt.get_resource("actions/add_file.png")), "", self
        )
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
            item.setCheckState(Qt.Checked)
            self.outputformats_list.addItem(item)

        layout = QVBoxLayout()
        layout.addWidget(self.outputformats_list)

        self.setLayout(layout)


class OutputOptionsWidget(QGroupBox):
    def __init__(self, title: str, *args, **kwargs):
        super().__init__(title, *args, **kwargs)

        self.multifile = QCheckBox("mehrere Dateien", self)

        layout = QHBoxLayout()
        layout.addWidget(self.multifile)

        self.setLayout(layout)


class UnderlaySettingsWidget(QGroupBox):
    def __init__(self, title: str, *args, **kwargs):
        super().__init__(title, *args, **kwargs)
        layout = QGridLayout()
        self.setLayout(layout)

        self.dpi = QSpinBox(self)
        self.dpi.setMaximum(600)
        self.dpi.setMinimum(72)
        self.dpi.setValue(Defaults.DPI)
        layout.addWidget(QLabel("Dokument DPI"), 0, 0)
        layout.addWidget(self.dpi, 0, 1)

        self.overlap = QSpinBox(self)
        self.overlap.setMinimum(0)
        self.overlap.setValue(Defaults.OVERLAP)
        layout.addWidget(QLabel("Überlagerung"), 1, 0)
        layout.addWidget(self.overlap, 1, 1)


class GlueMarkWidget(QGroupBox):
    def __init__(self, title: str, *args, **kwargs):

        super().__init__(title, *args, **kwargs)
        layout = QGridLayout()
        self.setLayout(layout)

        font_layout = QHBoxLayout(self)
        self.font_size = QSpinBox(self)
        self.font_size.setMinimum(5)
        self.font_size.setMaximum(100)
        self.font_size.setValue(Defaults.FONT_SIZE)

        self.font = QComboBox(self)
        for font in sorted(font_manager.ttflist, key=lambda x: x.face.name):
            self.font.addItem(
                QIcon(appctxt.get_resource("files/font.png")),
                font.face.name.decode("ascii"),
                font,
            )

        font_layout.addWidget(self.font, 3)
        font_layout.addWidget(self.font_size, 1)
        font_layout.setContentsMargins(0, 0, 0, 0)

        font_widget = QWidget(self)
        font_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        font_widget.setMaximumHeight(self.font.height())
        font_widget.setContentsMargins(0, 0, 0, 0)
        font_widget.setLayout(font_layout)
        layout.addWidget(QLabel("Schrift", self), 0, 0)
        layout.addWidget(font_widget, 0, 1, 1, 2)

        layout.addWidget(QLabel("Marker", self), 4, 0)
        self.marker_type_x = QComboBox(self)
        self.marker_type_y = QComboBox(self)

        for name, marker in MARKERS.items():
            marker_icon = QIcon(appctxt.get_resource(f"markers/{name}.png"))
            self.marker_type_x.addItem(marker_icon, name, marker)
            self.marker_type_y.addItem(marker_icon, name, marker)

        layout.addWidget(self.marker_type_x, 4, 1)
        layout.addWidget(self.marker_type_y, 4, 2)

        layout.addWidget(QLabel("Beschriftungen", self), 5, 0)
        self.marker_labels_x = QComboBox(self)
        self.marker_labels_y = QComboBox(self)

        for name, marker_set in MARKER_SETS.items():
            label_icon = QIcon(appctxt.get_resource(f"labels/{name}.png"))
            self.marker_labels_x.addItem(label_icon, name, marker_set)
            self.marker_labels_y.addItem(label_icon, name, marker_set)

        layout.addWidget(self.marker_labels_x, 5, 1)
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

        self.pages: Optional[Sequence[BytesIO]] = None
        self.current_page = 1
        self.zoom_factor = 1.0

        super().__init__(title, *args, **kwargs)
        layout = QVBoxLayout()
        self.setLayout(layout)

        scroller = QScrollArea(self)
        self.preview_box = QLabel(scroller)
        scroller.setWidget(self.preview_box)
        scroller.setAlignment(Qt.AlignCenter)
        layout.addWidget(scroller)

        control_layout = QHBoxLayout()
        self.button_zoom_fit = QPushButton(
            QIcon(appctxt.get_resource("actions/zoom_fit.png")), "", self
        )
        self.button_zoom_fit.clicked.connect(self.zoom_fit)
        self.button_zoom_out = QPushButton(
            QIcon(appctxt.get_resource("actions/zoom_out.png")), "", self
        )
        self.button_zoom_out.clicked.connect(
            lambda: self.set_zoom(self.zoom_factor * 0.9)
        )
        self.button_zoom_in = QPushButton(
            QIcon(appctxt.get_resource("actions/zoom_in.png")), "", self
        )
        self.button_zoom_in.clicked.connect(
            lambda: self.set_zoom(self.zoom_factor * 1.1)
        )
        control_layout.addWidget(self.button_zoom_fit)
        control_layout.addWidget(self.button_zoom_out)
        control_layout.addWidget(self.button_zoom_in)

        control_layout.addSpacing(100)

        self.button_prev_page = QPushButton(
            QIcon(appctxt.get_resource("actions/prev.png")), "", self
        )
        self.button_prev_page.clicked.connect(
            lambda: self.set_page(self.current_page - 1)
        )

        self.label_current_page = QLabel("", self)
        self.label_current_page.setAlignment(Qt.AlignCenter)

        self.button_next_page = QPushButton(
            QIcon(appctxt.get_resource("actions/next.png")), "", self
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
        self.update_preview()

    def set_loading(self):
        loader = QMovie(appctxt.get_resource("animations/loader.gif"))
        self.preview_box.setMovie(loader)
        loader.jumpToFrame(0)
        self.preview_box.resize(loader.currentImage().size())
        loader.start()

    def update_preview(self):
        if self.pages is not None:
            pdf_file = self.pages[self.current_page - 1]
            pdf_file.seek(0)
            document = Document(stream=pdf_file, filetype="PDF")
            image = QPixmap()

            page = document.loadPage(0)

            container_size = self.preview_box.parent().size()

            normalized_zoom_factor = min(
                page.rect.height / container_size.height(),
                page.rect.width / container_size.width(),
            )
            scale_mat = Matrix(normalized_zoom_factor, normalized_zoom_factor)

            image.loadFromData(page.getPixmap(matrix=scale_mat).getPNGData())
            image_size = container_size * self.zoom_factor
            self.preview_box.setPixmap(image.scaled(image_size, Qt.KeepAspectRatio))
            self.preview_box.resize(image_size)
        else:
            self.preview_box.setTextFormat(Qt.RichText)
            self.preview_box.setStyleSheet("QLabel { color : darkgray; }")
            self.preview_box.setText(
                f'<center><img src="{appctxt.get_resource("logo.png")}") /><br />Wähle auf der rechten Seite<br />eine Datei und ein Papierformat<br />aus um die Vorschau anzuzeigen</center>'
            )

            self.preview_box.resize(QSize(200, 200))

    def resizeEvent(self, event):
        self.update_preview()
        return super().resizeEvent(event)

    def update_controls(self):
        if self.pages:
            num_pages = len(self.pages)
            if self.current_page >= num_pages:
                self.current_page = num_pages

            self.label_current_page.setText(f"{self.current_page} / {num_pages}")
            self.button_prev_page.setEnabled(self.current_page != 1)
            self.button_next_page.setEnabled(self.current_page != num_pages)

    def set_preview_pages(self, pages):
        self.pages = pages
        self.update_controls()
        self.update_preview()

    def set_page(self, page):
        self.current_page = page
        self.update_preview()
        self.update_controls()

    def set_zoom(self, zoom_factor):
        self.zoom_factor = zoom_factor
        self.update_preview()
        self.update_controls()

    def zoom_fit(self):
        self.set_zoom(1.0)


class MainWindow(QMainWindow):
    marker_def = GlueMarkDefinition()
    underlay_def = UnderlayDefinition()

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Schnitt Tisch")
        self.setWindowIcon(QIcon("src/main/icons/Icon.ico"))
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

        self.outputoptions_box = OutputOptionsWidget("Ausgabepfad", self)

        self.underlaysettings_box = UnderlaySettingsWidget(
            "Dokumenteinstellungen", self
        )

        self.gluemarks_box = GlueMarkWidget("Klebehilfen", self)

        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self.outputoptions_box, 1)
        settings_layout.addWidget(self.underlaysettings_box, 2)
        settings_layout.addWidget(self.gluemarks_box, 5)

        settings_widget = QWidget(self)
        settings_widget.setLayout(settings_layout)
        settings_widget.setMaximumWidth(400)
        settings_widget.setMinimumWidth(350)

        preview_layout = QHBoxLayout()
        preview_widget_container = QWidget(self)
        preview_widget_container.setLayout(preview_layout)
        self.preview_widget = PreviewWidget("Vorschau", self)
        preview_layout.addWidget(self.preview_widget)

        action_button_layout = QHBoxLayout()

        site_link = QLabel('<a href="https://naehcram.de/">by Nähcram</a>')
        site_link.setTextFormat(Qt.RichText)
        site_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        site_link.setOpenExternalLinks(True)
        action_button_layout.addWidget(site_link, alignment=Qt.AlignLeft)

        self.export_button = QPushButton(
            QIcon(appctxt.get_resource("actions/save.png")), "Exportieren"
        )

        self.loadSettings()
        self.file_box.file_list.currentRowChanged.connect(self.updatePreview)
        self.outputformat_box.outputformats_list.currentRowChanged.connect(
            self.updatePreview
        )
        self.underlaysettings_box.dpi.valueChanged.connect(self.updatePreview)
        self.underlaysettings_box.overlap.valueChanged.connect(self.updatePreview)
        self.gluemarks_box.font.currentTextChanged.connect(self.updatePreview)
        self.gluemarks_box.font_size.valueChanged.connect(self.updatePreview)
        self.gluemarks_box.marker_type_x.currentTextChanged.connect(self.updatePreview)
        self.gluemarks_box.marker_type_y.currentTextChanged.connect(self.updatePreview)
        self.gluemarks_box.marker_labels_x.currentTextChanged.connect(
            self.updatePreview
        )
        self.gluemarks_box.marker_labels_y.currentTextChanged.connect(
            self.updatePreview
        )
        self.gluemarks_box.marker_inner_size.sliderReleased.connect(self.updatePreview)
        self.gluemarks_box.marker_outer_size.sliderReleased.connect(self.updatePreview)
        self.export_button.clicked.connect(self.exportPdf)
        self.file_box.file_list.model().rowsInserted.connect(self.update_export_state)
        self.file_box.file_list.model().rowsRemoved.connect(self.update_export_state)
        self.update_export_state()

        self.export_button.setFixedWidth(200)
        action_button_layout.addWidget(self.export_button, alignment=Qt.AlignRight)
        action_button_widget = QWidget(self)
        action_button_widget.setLayout(action_button_layout)

        self.setCentralWidget(preview_widget_container)
        left_widget = QDockWidget()
        left_widget.setWidget(io_widget)
        left_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)
        left_widget.setTitleBarWidget(QWidget(self))

        right_widget = QDockWidget()
        right_widget.setWidget(settings_widget)
        right_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)
        right_widget.setTitleBarWidget(QWidget(self))

        bottom_widget = QDockWidget()
        bottom_widget.setWidget(action_button_widget)
        bottom_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)
        bottom_widget.setTitleBarWidget(QWidget(self))
        bottom_widget.setMaximumHeight(50)
        bottom_widget.setMinimumHeight(50)

        self.addDockWidget(Qt.LeftDockWidgetArea, left_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, right_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom_widget)

    def init_menu(self):
        exportAction = QAction("Exportieren", self)
        exportAction.setShortcut("Ctrl+Shift+S")
        exportAction.triggered.connect(self.exportPdf)

        exitAct = QAction("Quit", self)
        exitAct.setShortcut("Ctrl+Q")
        exitAct.triggered.connect(app.quit)

        menubar = self.menuBar()
        fileMenu = menubar.addMenu("&File")
        fileMenu.addAction(exportAction)
        fileMenu.addSeparator()
        fileMenu.addAction(exitAct)

        helpMenu = menubar.addMenu("&Help")
        aboutAct = QAction("Über", self)
        aboutAct.setShortcut("Ctrl+?")
        aboutText = f'<big>Schnitt Tisch</big><br /><small>v{VERSION}</small><br /><a href="https://naehcram.de/">by Nähcram</a>'
        aboutAct.triggered.connect(
            lambda: QMessageBox.about(self, self.windowTitle(), aboutText)
        )
        helpMenu.addAction(aboutAct)

    def updatePreview(self):

        self.updateSettings()
        input_file_index = self.file_box.file_list.currentRow()
        outputformat_item = self.outputformat_box.outputformats_list.currentItem()

        if input_file_index < 0 or outputformat_item is None:
            self.preview_widget.set_preview_pages(None)
        else:

            def asyncUpdatePreview():
                selected_input_file = self.file_box.file_list.paths[input_file_index]

                output_pages = posterize_pdf(
                    selected_input_file,
                    PAGE_SIZES[outputformat_item.text()],
                    self.underlay_def.overlap,
                    self.underlay_def.dpi,
                    self.marker_def,
                )
                self.preview_widget.set_preview_pages(output_pages)

            self.preview_widget.set_loading()
            updater = Thread(target=asyncUpdatePreview)
            updater.start()

    def updateSettings(self):
        font = self.gluemarks_box.font.currentData()
        self.marker_def.font = font

        self.marker_def.font_size = self.gluemarks_box.font_size.value()
        self.marker_def.marker_x = self.gluemarks_box.marker_type_x.currentData()
        self.marker_def.marker_y = self.gluemarks_box.marker_type_y.currentData()
        self.marker_def.label_x = self.gluemarks_box.marker_labels_x.currentData()
        self.marker_def.label_y = self.gluemarks_box.marker_labels_y.currentData()
        self.marker_def.size = Size(
            self.gluemarks_box.marker_inner_size.value(),
            self.gluemarks_box.marker_outer_size.value(),
        )

        self.underlay_def.overlap = self.underlaysettings_box.overlap.value()
        self.underlay_def.dpi = self.underlaysettings_box.dpi.value()
        self.saveSettings()

    def saveSettings(self):
        settings.setValue("marker_def/font", self.gluemarks_box.font.currentText())
        settings.setValue("marker_def/font_size", self.marker_def.font_size)
        settings.setValue(
            "marker_def/marker_x", self.gluemarks_box.marker_type_x.currentText()
        )
        settings.setValue(
            "marker_def/marker_y", self.gluemarks_box.marker_type_y.currentText()
        )
        settings.setValue(
            "marker_def/label_x", self.gluemarks_box.marker_labels_x.currentText()
        )
        settings.setValue(
            "marker_def/label_y", self.gluemarks_box.marker_labels_y.currentText()
        )
        settings.setValue("marker_def/size/inner", self.marker_def.size.x)
        settings.setValue("marker_def/size/outer", self.marker_def.size.y)
        settings.setValue("underlay_def/overlap", self.underlay_def.overlap)
        settings.setValue("underlay_def/dpi", self.underlay_def.dpi)
        settings.setValue("multifile", self.outputoptions_box.multifile.isChecked())

    def loadSettings(self):
        self.gluemarks_box.font.setCurrentText(
            settings.value(
                "marker_def/font",
                self.gluemarks_box.font.currentData().face.name.decode("ascii"),
            )
        )
        self.gluemarks_box.font_size.setValue(
            int(settings.value("marker_def/font_size", Defaults.FONT_SIZE))
        )
        self.gluemarks_box.marker_type_x.setCurrentText(
            settings.value("marker_def/marker_x", list(MARKERS.keys())[0])
        )
        self.gluemarks_box.marker_type_y.setCurrentText(
            settings.value("marker_def/marker_y", list(MARKERS.keys())[0])
        )
        self.gluemarks_box.marker_labels_x.setCurrentText(
            settings.value("marker_def/label_x", list(MARKER_SETS.keys())[0])
        )
        self.gluemarks_box.marker_labels_y.setCurrentText(
            settings.value("marker_def/label_y", list(MARKER_SETS.keys())[0])
        )
        self.gluemarks_box.marker_inner_size.setValue(
            int(settings.value("marker_def/size/inner", Defaults.MARKER_SIZE.x))
        )
        self.gluemarks_box.marker_outer_size.setValue(
            int(settings.value("marker_def/size/outer", Defaults.MARKER_SIZE.y))
        )
        self.underlaysettings_box.overlap.setValue(
            int(settings.value("underlay_def/overlap", Defaults.OVERLAP))
        )
        self.underlaysettings_box.dpi.setValue(
            int(settings.value("underlay_def/dpi", Defaults.DPI))
        )
        self.outputoptions_box.multifile.setChecked(
            bool(settings.value("multifile", False))
        )

    def exportPdf(self):

        input_file_index = self.file_box.file_list.currentRow()
        preselected_folder = ""
        if input_file_index >= 0:
            preselected_folder = Path(
                self.file_box.file_list.paths[input_file_index]
            ).parent
        folder = QFileDialog.getExistingDirectory(
            self, "Ausgabeordner wählen", str(preselected_folder)
        )

        multipage = self.outputoptions_box.multifile.isChecked()
        format_list = self.outputformat_box.outputformats_list
        output_formats = [
            format_list.item(x).text()
            for x in range(format_list.count())
            if format_list.item(x).checkState() == Qt.Checked
        ]

        if not folder:
            return
        folder = Path(folder)
        needs_force = False
        output_pages = {}
        output_files = {}
        for in_file in self.file_box.file_list.paths:
            for format in output_formats:
                file_key = f"{in_file.stem}_{format}"
                output_pages[file_key] = posterize_pdf(
                    in_file,
                    PAGE_SIZES[format],
                    self.underlay_def.overlap,
                    self.underlay_def.dpi,
                    self.marker_def,
                )

                output_files[file_key] = get_save_paths(
                    folder, file_key, multipage, output_pages[file_key]
                )
                needs_force = any(
                    os.path.exists(output_file)
                    for output_file in output_files[file_key]
                )

        if needs_force:
            do_override = QMessageBox.question(
                self,
                "Ausgabeverzeichnis existiert",
                "Ausgabepfad existiert bereits, überschreiben?",
            )

        if not needs_force or do_override:
            for file_key, out_pages in output_pages.items():
                out_files = output_files[file_key]
                save_output(out_files, out_pages)

    def update_export_state(self):
        enabled = self.file_box.file_list.model().rowCount() > 0
        self.export_button.setEnabled(enabled)


if __name__ == "__main__":
    appctxt = ApplicationContext()
    app = appctxt.app
    settings = QSettings("Schnitt Tisch", "Naehcram")

    main_window = MainWindow()
    main_window.show()

    exit_code = app.exec_()
    sys.exit(exit_code)
