"""Fit the main window to whatever screen it is on: any resolution, any scaling, any monitor.

Qt layouts squeeze widgets on top of each other when a window is shorter or narrower than the
layout's minimum, which happens on small or highly scaled screens. Two things prevent that:
the window content scrolls instead of overlapping, and the window opens (and stays) inside the
usable area of its current screen, excluding the taskbar or dock.
"""
from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QTimer
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

# Share of the usable screen the window may take, leaving room for the frame and the desktop.
SCREEN_SHARE = 0.92
# Smallest window; anything the layout needs beyond this scrolls.
MINIMUM = (420, 320)


def scrollable(content):
    """Wrap window content so a screen smaller than the layout scrolls instead of overlapping widgets."""
    area = QScrollArea()
    area.setObjectName('screenfit')
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(content)
    return area


def scroll_body(dialog):
    """Give a dialog a scrollable body and return the widget to build its content in."""
    shell = QVBoxLayout(dialog)
    shell.setContentsMargins(0, 0, 0, 0)
    body = QWidget()
    body.setObjectName('screenfitBody')
    shell.addWidget(scrollable(body))
    return body


def content(window):
    """The widget holding the window's layout, whether or not it is wrapped for scrolling."""
    central = window.centralWidget()
    return central.widget() if isinstance(central, QScrollArea) else central


def fitted_size(width, height, available):
    """Preferred size, shrunk to the usable part of the screen when that is smaller."""
    return (max(MINIMUM[0], min(width, int(available.width() * SCREEN_SHARE))),
            max(MINIMUM[1], min(height, int(available.height() * SCREEN_SHARE))))


class _KeepOnScreen(QObject):
    """Each time the window is shown, move its real frame (title bar included, only known once shown) fully onto its screen."""
    def eventFilter(self, window, event):
        if event.type() == QEvent.Show:
            QTimer.singleShot(0, lambda: keep_on_screen(window))
        return False


def keep_on_screen(window):
    screen = window.screen()
    if screen is None or window.isMaximized() or window.isFullScreen():
        return
    available, frame = screen.availableGeometry(), window.frameGeometry()
    if frame.height() > available.height() or frame.width() > available.width():
        extra = frame.size() - QWidget.size(window)
        window.resize(min(QWidget.size(window).width(), available.width() - extra.width()),
                      min(QWidget.size(window).height(), available.height() - extra.height()))
        frame = window.frameGeometry()
    x = min(max(frame.left(), available.left()), available.right() - frame.width() + 1)
    y = min(max(frame.top(), available.top()), available.bottom() - frame.height() + 1)
    if (x, y) != (frame.left(), frame.top()):
        window.move(x, y)


def fit(window, width, height, screen=None):
    """Open at the preferred size or smaller, centred on its parent window (or the screen), and keep fitting when it moves to another screen."""
    window.setMinimumSize(*MINIMUM)
    screen = screen or window.screen()
    if screen is None:
        window.resize(width, height)
        return
    available = screen.availableGeometry()
    w, h = fitted_size(width, height, available)
    window.resize(w, h)
    parent = window.parentWidget()
    centre = parent.window().frameGeometry().center() if parent is not None and parent.isVisible() else available.center()
    x = min(max(centre.x() - w // 2, available.left()), available.right() - w)
    y = min(max(centre.y() - h // 2, available.top()), available.bottom() - h)
    window.move(x, y)
    window._screenfit = _KeepOnScreen(window)
    window.installEventFilter(window._screenfit)
    window.winId()  # creates the native window so the screen change signal exists before show
    handle = window.windowHandle()
    if handle is not None:
        handle.screenChanged.connect(lambda new: shrink_to(window, new))


def shrink_to(window, screen):
    """After moving to a smaller or more scaled screen, shrink (never grow) so the whole window stays reachable."""
    if screen is None or window.isMaximized() or window.isFullScreen():
        return
    available = screen.availableGeometry()
    # QWidget.size(), not width()/height(): windows may name their own attributes width or height.
    current = QWidget.size(window)
    w, h = fitted_size(current.width(), current.height(), available)
    if (w, h) != (current.width(), current.height()):
        window.resize(w, h)
        frame = QRect(window.pos(), window.frameGeometry().size())
        if not available.contains(frame):
            window.move(available.center() - QPoint(w // 2, h // 2))
