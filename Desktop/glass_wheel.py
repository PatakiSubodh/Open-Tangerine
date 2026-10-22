"""Accessible in-window version of the floating glass wheel."""
import math
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget, QPushButton
from glass_design import draw_ring, draw_hub, target_at


class GlassWheel(QWidget):
    selected = Signal(str)
    formats = ('PNG', 'JPEG', 'WEBP', 'TIFF', 'BMP', 'Image → PDF')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 360)
        self.setAccessibleName('Glass conversion wheel')
        self.current = 'PNG'
        self.buttons = []
        for label in self.formats:
            button = QPushButton('', self)
            button.setCheckable(True)
            button.setAccessibleName('Convert to ' + label)
            button.setToolTip('Convert to ' + label)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, value=label: self.selected.emit(value))
            self.buttons.append(button)
        self.set_current(self.current)

    def set_current(self, value):
        self.current = value
        for label, button in zip(self.formats, self.buttons):
            button.setChecked(label == value)
        self.update()

    def geometry_scale(self):
        return min(self.width()/380, self.height()/425)

    def resizeEvent(self, event):
        scale = self.geometry_scale()
        left = (self.width()-380*scale)/2
        for index, button in enumerate(self.buttons):
            angle = math.radians(index * 60 - 90)
            button.setGeometry(round(left+(190+math.cos(angle)*123-40)*scale),
                               round((190+math.sin(angle)*123-22)*scale), round(80*scale), round(44*scale))
        super().resizeEvent(event)

    def mouseReleaseEvent(self, event):
        scale = self.geometry_scale(); left = (self.width()-380*scale)/2
        index = target_at(QPointF((event.position().x()-left)/scale, event.position().y()/scale), self.formats)
        if event.button() == Qt.LeftButton and index >= 0:
            self.selected.emit(self.formats[index])
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        scale = self.geometry_scale()
        p.translate((self.width()-380*scale)/2, 0); p.scale(scale, scale)
        selected = self.formats.index(self.current) if self.current in self.formats else -1
        draw_ring(p, self.formats, selected)
        draw_hub(p, [self.current] if selected < 0 else self.formats, selected)


WHEEL_STYLE = '''
GlassWheel QPushButton { background: transparent; border: none; padding: 0; }
GlassWheel QPushButton:focus { border: 2px solid #ffffff; border-radius: 12px; }
'''
