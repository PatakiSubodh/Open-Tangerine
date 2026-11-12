"""Fit the main window to whatever screen it is on: any resolution, any scaling, any monitor.

Qt layouts squeeze widgets on top of each other when a window is shorter or narrower than the
layout's minimum, which happens on small or highly scaled screens. Two things prevent that:
the window content scrolls instead of overlapping, and the window opens (and stays) inside the
usable area of its current screen, excluding the taskbar or dock.
"""
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget

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


def content(window):
    """The widget holding the window's layout, whether or not it is wrapped for scrolling."""
    central = window.centralWidget()
    return central.widget() if isinstance(central, QScrollArea) else central


def fitted_size(width, height, available):
    """Preferred size, shrunk to the usable part of the screen when that is smaller."""
    return (max(MINIMUM[0], min(width, int(available.width() * SCREEN_SHARE))),
            max(MINIMUM[1], min(height, int(available.height() * SCREEN_SHARE))))


def fit(window, width, height, screen=None):
    """Open at the preferred size or smaller, centred on the screen, and keep fitting when it moves to another screen."""
    window.setMinimumSize(*MINIMUM)
    screen = screen or window.screen()
    if screen is None:
        window.resize(width, height)
        return
    available = screen.availableGeometry()
    w, h = fitted_size(width, height, available)
    window.resize(w, h)
    window.move(available.center() - QPoint(w // 2, h // 2))
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
