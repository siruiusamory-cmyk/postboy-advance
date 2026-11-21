"""The Help menu's targets, the About box, and the dialog an unhandled error opens."""

from __future__ import annotations

from http.client import HTTPException
import json
import logging
from pathlib import Path
import platform
import re
import sys
import traceback
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

import PySide6
from PySide6.QtCore import Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from ..model.jobs import REPOSITORY_ROOT

log = logging.getLogger("postboy-advance")
REPOSITORY_URL = "https://github.com/siruiusamory-cmyk/postboy-advance"
GUIDE_URL = REPOSITORY_URL + "/blob/master/docs/creator.md"
NEW_ISSUE_URL = REPOSITORY_URL + "/issues/new"
RELEASES_URL = REPOSITORY_URL + "/releases"
LATEST_RELEASE_API = REPOSITORY_URL.replace("github.com", "api.github.com/repos") + "/releases/latest"
URL_LIMIT = 6000
TITLE_LIMIT = 120
NEVER_ATTACH = "Never attach a ROM, save file or anything taken out of the game."
DISCLAIMER = (
    "Postboy Advance is a fan-made tool. It is not affiliated with or endorsed by the "
    "owners of Dragon Ball Z or the publishers of the games, and it contains no game data."
)


def open_url(url: QUrl) -> bool:
    """Every link and folder the program opens goes through here."""
    return QDesktopServices.openUrl(url)


def beside_program(name: str) -> Path:
    """A file the release zip puts beside the program, or the checkout's copy of it."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / name
    return REPOSITORY_ROOT / name


def short_path(path: str) -> str:
    """The 8.3 spelling Windows reports for a path, or the path where there is none."""
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(path, buffer, len(buffer)):
            return buffer.value
    except (AttributeError, OSError):
        pass
    return path


def without_home(text: str) -> str:
    home = Path.home()
    spellings = [urlsplit(home.as_uri()).path]
    for base in dict.fromkeys((str(home), short_path(str(home)))):
        # An OSError prints doubled backslashes, and a repr of that text doubles them again.
        spellings += [base.replace("\\", "\\\\\\\\"), base.replace("\\", "\\\\"), base,
                      base.replace("\\", "/")]
    for spelling in spellings:
        text = re.sub(re.escape(spelling), "~", text, flags=re.IGNORECASE)
    return text


def details_text(identity: dict) -> str:
    """The plain-text facts a bug report needs; About and the error dialog share it."""
    product, build = identity.get("product", {}), identity.get("build", {})
    commit = build.get("commit")
    lines = [
        " ".join(part for part in (product.get("name"), product.get("version")) if part),
        f"Commit: {commit}" + (" (modified tree)" if build.get("dirty") else "") if commit else "",
        f"Built: {build['built_at']}" if build.get("built_at") else "",
        f"Python {platform.python_version()}",
        f"PySide6 {PySide6.__version__}, Qt {qVersion()}",
        platform.platform(),
    ]
    return without_home("\n".join(line for line in lines if line))


def issue_url(details: str, title: str = "", trace: str = "") -> str:
    """A pre-filled new-issue link, cut to fit by dropping the oldest traceback lines."""
    title, trace = without_home(title)[:TITLE_LIMIT], without_home(trace)

    def build(tail: str) -> str:
        body = "\n\n".join(part for part in (without_home(details), tail, NEVER_ATTACH) if part)
        return NEW_ISSUE_URL + "?" + urlencode({"title": title, "body": body}, quote_via=quote)

    low, high = 0, len(trace)
    while low < high:
        middle = (low + high + 1) // 2
        if len(build(trace[len(trace) - middle:])) <= URL_LIMIT:
            low = middle
        else:
            high = middle - 1
    tail = trace[len(trace) - low:]
    if low < len(trace) and "\n" in tail:
        tail = tail.split("\n", 1)[1]
    return build(tail)


def version_key(text: str) -> tuple:
    """A dev build sorts before its release; text that is not a version sorts lowest."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?", text.strip())
    if not match:
        return ()
    *numbers, dev = match.groups()
    return (*map(int, numbers), dev is None, int(dev or 0))


def latest_release() -> str:
    """The tag of the newest published release, asked of GitHub."""
    request = Request(LATEST_RELEASE_API, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "Postboy-Advance"})
    with urlopen(request, timeout=10) as reply:
        return str(json.load(reply)["tag_name"])[:40]


def check_for_updates(window, identity: dict) -> None:
    current = identity.get("product", {}).get("version", "")
    QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        # shortcut: blocks the window for up to ten seconds, move to a thread if that is felt
        latest = latest_release()
    except (OSError, HTTPException, ValueError, KeyError, TypeError) as error:
        log.warning("update check failed: %s", without_home(str(error)))
        latest = None
    finally:
        QGuiApplication.restoreOverrideCursor()
    if latest is None:
        text = ("Could not check for updates. Check your internet connection, or open "
                "the download page to look yourself.")
    elif version_key(latest) > version_key(current):
        text = f"Postboy Advance {latest.removeprefix('v')} is available. You have {current}."
    else:
        text = f"You have the newest version, {current}. The newest release is {latest}."
    box = QMessageBox(QMessageBox.Icon.Information, "Check for Updates", text, parent=window)
    box.setTextFormat(Qt.TextFormat.PlainText)
    download = box.addButton("Open Download Page", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is download:
        open_url(QUrl(RELEASES_URL))


def _licence() -> str:
    try:
        with beside_program("LICENSE").open(encoding="utf-8") as handle:
            return handle.readline().strip()
    except OSError:
        return ""


def show_about(window, identity: dict) -> None:
    product, build = identity.get("product", {}), identity.get("build", {})
    version = ", ".join(part for part in (
        f"Version {product['version']}" if product.get("version") else "",
        f"commit {build['commit'][:12]}" if build.get("commit") else "",
        f"built {build['built_at']}" if build.get("built_at") else "",
    ) if part)
    licence = _licence()
    text = "\n\n".join(part for part in (
        product.get("name", ""), version, DISCLAIMER,
        f"Licence: {licence}" if licence else "", REPOSITORY_URL,
    ) if part)
    box = QMessageBox(QMessageBox.Icon.Information, "About Postboy Advance", text, parent=window)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    copy = box.addButton("Copy details", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is copy:
        QGuiApplication.clipboard().setText(details_text(identity))


def show_error(window, kind, value, trace) -> None:
    summary = f"{kind.__name__}: {value}"
    written = without_home("".join(traceback.format_exception(kind, value, trace)))
    details = details_text(window.identity)
    box = QMessageBox(
        QMessageBox.Icon.Warning,
        "Something went wrong",
        "Something went wrong in Postboy Advance. You can copy the details or report them "
        "on GitHub. If the program closes before you save, your unsaved text changes are "
        f"offered back the next time you open the project.\n\n{summary}",
        parent=window,
    )
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setDetailedText(written)
    report = box.addButton("Report on GitHub", QMessageBox.ButtonRole.ActionRole)
    copy = box.addButton("Copy details", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is report:
        open_url(QUrl(issue_url(details, summary, written)))
    elif box.clickedButton() is copy:
        QGuiApplication.clipboard().setText(f"{details}\n\n{written}")


class ErrorHook:
    """sys.excepthook: log every unhandled error, and show one at a time in the window."""

    def __init__(self, window=None) -> None:
        self.window = window
        self.showing = False

    def __call__(self, kind, value, trace) -> None:
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, trace)
            return
        log.error("unhandled error", exc_info=(kind, value, trace))
        window = self.window
        if self.showing or window is None or window.quiet or QApplication.instance() is None:
            return
        self.showing = True
        try:
            show_error(window, kind, value, trace)
        except Exception:
            log.exception("the error dialog could not be shown")
        finally:
            self.showing = False
