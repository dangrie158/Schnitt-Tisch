import sys
import os
import logging
import subprocess
from threading import Timer
from functools import lru_cache
from pathlib import Path
from reportlab.pdfbase.ttfonts import TTFont, TTFError

_log = logging.getLogger(__name__)

TTFSynonyms = ['otf', 'ttc', 'ttf']
MSFolders = \
    r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
MSFontDirectories = [
    r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts',
    r'SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts']
MSUserFontDirectories = [
    str(Path.home() / 'AppData/Local/Microsoft/Windows/Fonts'),
    str(Path.home() / 'AppData/Roaming/Microsoft/Windows/Fonts'),
]
X11FontDirectories = [
    # an old standard installation point
    "/usr/X11R6/lib/X11/fonts/TTF/",
    "/usr/X11/lib/X11/fonts",
    # here is the new standard location for fonts
    "/usr/share/fonts/",
    # documented as a good place to install new fonts
    "/usr/local/share/fonts/",
    # common application, not really useful
    "/usr/lib/openoffice/share/fonts/truetype/",
    # user fonts
    str(Path(os.environ.get('XDG_DATA_HOME',
                            Path.home() / ".local/share")) / "fonts"),
    str(Path.home() / ".fonts"),
]
OSXFontDirectories = [
    "/Library/Fonts/",
    "/Network/Library/Fonts/",
    "/System/Library/Fonts/",
    # fonts installed via MacPorts
    "/opt/local/share/fonts",
    # user fonts
    str(Path.home() / "Library/Fonts"),
]

def win32FontDirectory():
    r"""
    Return the user-specified font directory for Win32.  This is
    looked up from the registry key ::
      \\HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders\Fonts
    If the key is not found, ``%WINDIR%\Fonts`` will be returned.
    """
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MSFolders) as user:
            return winreg.QueryValueEx(user, 'Fonts')[0]
    except OSError:
        return os.path.join(os.environ['WINDIR'], 'Fonts')

def _win32RegistryFonts(reg_domain, base_dir):
    r"""
    Searches for fonts in the Windows registry.
    Parameters
    ----------
    reg_domain : int
        The top level registry domain (e.g. HKEY_LOCAL_MACHINE).
    base_dir : str
        The path to the folder where the font files are usually located (e.g.
        C:\Windows\Fonts). If only the filename of the font is stored in the
        registry, the absolute path is built relative to this base directory.
    Returns
    -------
    `set`
        `pathlib.Path` objects with the absolute path to the font files found.
    """
    import winreg
    items = set()

    for reg_path in MSFontDirectories:
        try:
            with winreg.OpenKey(reg_domain, reg_path) as local:
                for j in range(winreg.QueryInfoKey(local)[1]):
                    # value may contain the filename of the font or its
                    # absolute path.
                    key, value, tp = winreg.EnumValue(local, j)
                    if not isinstance(value, str):
                        continue

                    # Work around for https://bugs.python.org/issue25778, which
                    # is fixed in Py>=3.6.1.
                    value = value.split("\0", 1)[0]

                    try:
                        # If value contains already an absolute path, then it
                        # is not changed further.
                        path = Path(base_dir, value).resolve()
                    except RuntimeError:
                        # Don't fail with invalid entries.
                        continue

                    items.add(path)
        except (OSError, MemoryError):
            continue

    return items

def win32InstalledFonts(directory=None):
    """
    Search for fonts in the specified font directory, or use the
    system directories if none given. Additionally, it is searched for user
    fonts installed. A list of TrueType font filenames are returned
    """
    import winreg

    if directory is None:
        directory = win32FontDirectory()

    fontext = [f'.{ext}' for ext in TTFSynonyms]

    items = set()

    # System fonts
    items.update(_win32RegistryFonts(winreg.HKEY_LOCAL_MACHINE, directory))

    # User fonts
    for userdir in MSUserFontDirectories:
        items.update(_win32RegistryFonts(winreg.HKEY_CURRENT_USER, userdir))

    # Keep only paths with matching file extension.
    return [str(path) for path in items if path.suffix.lower() in fontext]

@lru_cache()
def _call_fc_list():
    """Cache and list the font filenames known to `fc-list`.
    """
    # Delay the warning by 5s.
    timer = Timer(5, lambda: _log.warning(
        'Matplotlib is building the font cache using fc-list. '
        'This may take a moment.'))
    timer.start()
    try:
        if b'--format' not in subprocess.check_output(['fc-list', '--help']):
            _log.warning(  # fontconfig 2.7 implemented --format.
                'Matplotlib needs fontconfig>=2.7 to query system fonts.')
            return []
        out = subprocess.check_output(['fc-list', '--format=%{file}\\n'])
    except (OSError, subprocess.CalledProcessError):
        return []
    finally:
        timer.cancel()
    return [os.fsdecode(fname) for fname in out.split(b'\n')]

def get_fontconfig_fonts():
    """List the font filenames known to `fc-list` having the given extension.
    """
    fontext = ['.' + ext for ext in TTFSynonyms]
    return [fname for fname in _call_fc_list()
            if Path(fname).suffix.lower() in fontext]

def list_fonts(directory, extensions):
    """
    Return a list of all fonts matching any of the extensions, found
    recursively under the directory.
    """
    extensions = ["." + ext for ext in extensions]
    return [os.path.join(dirpath, filename)
            # os.walk ignores access errors, unlike Path.glob.
            for dirpath, _, filenames in os.walk(directory)
            for filename in filenames
            if Path(filename).suffix.lower() in extensions]

def findSystemFonts(fontpaths=None):
    """
    Search for fonts in the specified font paths.  If no paths are
    given, will use a standard set of system paths, as well as the
    list of fonts tracked by fontconfig if fontconfig is installed and
    available.  A list of TrueType fonts are returned by default with
    AFM fonts as an option.
    """
    fontfiles = set()

    if fontpaths is None:
        if sys.platform == 'win32':
            fontpaths = MSUserFontDirectories + [win32FontDirectory()]
            # now get all installed fonts directly...
            fontfiles.update(win32InstalledFonts())
        else:
            fontpaths = X11FontDirectories
            if sys.platform == 'darwin':
                fontpaths = [*X11FontDirectories, *OSXFontDirectories]
            fontfiles.update(get_fontconfig_fonts())

    elif isinstance(fontpaths, str):
        fontpaths = [fontpaths]

    for path in fontpaths:
        fontfiles.update(map(os.path.abspath, list_fonts(path, TTFSynonyms)))

    return [fname for fname in fontfiles if os.path.exists(fname)]

class FontManager:
    """
    On import, the `FontManager` singleton instance creates a list of ttf 
    fonts and caches their `TTFFont`.
    """
    # Increment this version number whenever the font cache data
    # format or behavior has changed and requires a existing font
    # cache files to be rebuilt.
    def __init__(self, size=None, weight='normal'):

        paths = []
        for pathname in ['TTFPATH', 'AFMPATH']:
            if pathname in os.environ:
                ttfpath = os.environ[pathname]
                if ttfpath.find(';') >= 0:  # win32 style
                    paths.extend(ttfpath.split(';'))
                elif ttfpath.find(':') >= 0:  # unix style
                    paths.extend(ttfpath.split(':'))
                else:
                    paths.append(ttfpath)

        self.ttflist = []
        for path in [*findSystemFonts(paths),
                        *findSystemFonts()]:
            try:
                self.addfont(path)
            except OSError as exc:
                _log.info("Failed to open font file %s: %s", path, exc)
            except Exception as exc:
                _log.info("Failed to extract font properties from %s: %s",
                            path, exc)

    def addfont(self, path):
        prop = TTFont(path, path)
        self.ttflist.append(prop)

font_manager = FontManager()