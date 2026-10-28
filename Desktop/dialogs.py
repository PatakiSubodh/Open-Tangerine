"""Small themed dialogs: the scrollable information sheet."""
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget
import theme

class InfoDialog(QDialog):
    """A titled sheet of sections (heading + paragraph), scrollable, with one Close button."""
    def __init__(self, title, intro, sections, parent=None):
        super().__init__(parent);self.setWindowTitle(title);self.resize(640, 620)
        root = QVBoxLayout(self);root.setContentsMargins(22, 18, 22, 16);root.setSpacing(10)
        root.addWidget(theme.label(title, 'title'));root.addWidget(theme.label(intro, 'muted', True))
        area = QScrollArea();area.setWidgetResizable(True);area.setFrameShape(QScrollArea.NoFrame);root.addWidget(area, 1)
        body = QWidget();inner = QVBoxLayout(body);inner.setContentsMargins(0, 0, 8, 0);inner.setSpacing(10);area.setWidget(body)
        for heading, text in sections:
            frame, box = theme.card();box.addWidget(theme.label(heading.upper(), 'heading'));box.addWidget(theme.label(text, '', True));inner.addWidget(frame)
        inner.addStretch(1)
        row = QHBoxLayout();row.addStretch(1);root.addLayout(row)
        close = QPushButton('Close');close.setProperty('primary', True);close.clicked.connect(self.accept);row.addWidget(close)
