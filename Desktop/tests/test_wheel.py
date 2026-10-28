import math, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QMimeData, QPoint, QPointF, QSettings, QUrl
from PySide6.QtGui import QCursor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PIL import Image
import wheel, actions
from wheel import DragDetector, DragWatcher, Sample, WheelOverlay, WheelController, Notch, targets_for, items_for, mode_of, MODES

def pump(app, seconds=.05):
    end = time.monotonic() + seconds
    while time.monotonic() < end: app.processEvents();time.sleep(.005)

class TargetTests(unittest.TestCase):
    def test_images(self):
        t = targets_for(['a.PNG', 'b.heic', 'c.svg']);self.assertEqual(t[:2], ['PNG', 'JPEG']);self.assertIn('Image → PDF', t);self.assertIn('OCR → Text', t);self.assertEqual(t[-1], 'SHA-256');self.assertLessEqual(len(t), 12)
    def test_pdf_merge_only_for_several(self):
        self.assertNotIn('Merge PDFs', targets_for(['a.pdf']));self.assertIn('Merge PDFs', targets_for(['a.pdf', 'b.pdf']))
    def test_other_kinds(self):
        self.assertEqual(targets_for(['a.docx']), ['Office → PDF', 'SHA-256']);self.assertEqual(targets_for(['a.srt'])[0], 'SRT → VTT');self.assertEqual(targets_for(['a.vtt'])[0], 'VTT → SRT')
        self.assertIn('MP3', targets_for(['a.mp4']));self.assertEqual(targets_for(['mystery.xyz']), ['SHA-256'])
    def test_mixed_uses_common_operations(self):
        self.assertEqual(targets_for(['a.png', 'b.pdf']), ['Files → PDF', 'Files → DOCX', 'OCR → Text', 'OCR → Searchable PDF', 'SHA-256']);self.assertEqual(targets_for(['a.png', 'b.docx']), ['Files → PDF', 'SHA-256']);self.assertEqual(targets_for([]), [])
        self.assertEqual(targets_for(['a.mp3', 'b.png']), ['SHA-256']);self.assertNotIn('Files → PDF', targets_for(['a.pdf', 'b.pdf']));self.assertNotIn('Files → PDF', targets_for(['a.png', 'b.jpg']))
    def test_combine_is_offered_only_for_several_files(self):
        self.assertEqual(wheel.combine_target('Image → PDF', ['a.png', 'b.png']), 'Combine → PDF');self.assertEqual(wheel.combine_target('PDF → DOCX', ['a.pdf', 'b.pdf']), 'Combine → DOCX')
        self.assertIsNone(wheel.combine_target('Image → PDF', ['a.png']));self.assertIsNone(wheel.combine_target('JPEG', ['a.png', 'b.png']));self.assertIsNone(wheel.combine_target('Merge PDFs', ['a.pdf', 'b.pdf']))

class ModeItemTests(unittest.TestCase):
    def test_modifier_mapping(self):
        self.assertEqual(mode_of(True, False, False), 'convert');self.assertEqual(mode_of(False, True, False), 'tools');self.assertEqual(mode_of(True, True, False), 'tools')
        self.assertEqual(mode_of(True, False, True), 'actions');self.assertIsNone(mode_of(False, False, True), 'Ctrl alone is Explorer copy and must not open the wheel');self.assertIsNone(mode_of(False, False, False))
    def test_items_per_mode(self):
        files = ['a.png']
        self.assertEqual({i.kind for i in items_for('convert', files)}, {'convert'})
        tools = items_for('tools', files);self.assertEqual({i.kind for i in tools}, {'tool'});self.assertIn('crop_image', [i.key for i in tools])
        acts = items_for('actions', files);self.assertEqual([i.key for i in acts], ['reveal', 'copy_files', 'copy_paths', 'duplicate', 'hash'])
        self.assertEqual(items_for('tools', []), []);self.assertEqual(items_for('tools', ['a.png', 'b.pdf']), [])
        self.assertTrue(all(i.label and i.caption for m in MODES for i in items_for(m, files)))

class DetectorTests(unittest.TestCase):
    def feed(self, steps):
        d = DragDetector();return [d.update(Sample(pos, left, shift, ok, alt, ctrl)) for pos, left, shift, ok, alt, ctrl in steps]
    def test_shift_drag_engages_then_releases(self):
        out = self.feed([((0, 0), False, False, True, False, False), ((0, 0), True, False, True, False, False), ((20, 0), True, False, True, False, False), ((30, 0), True, True, True, False, False), ((40, 0), True, True, True, False, False), ((40, 0), False, True, True, False, False)])
        self.assertEqual(out, [None, None, None, ('engage', 'convert'), None, ('release', None)])
    def test_alt_opens_tools_and_ctrl_shift_opens_actions(self):
        self.assertEqual(self.feed([((0, 0), True, False, True, True, False), ((40, 0), True, False, True, True, False)])[-1], ('engage', 'tools'))
        self.assertEqual(self.feed([((0, 0), True, True, True, False, True), ((40, 0), True, True, True, False, True)])[-1], ('engage', 'actions'))
    def test_ctrl_alone_never_engages(self):
        out = self.feed([((0, 0), True, False, True, False, True), ((60, 0), True, False, True, False, True), ((90, 0), True, False, True, False, True), ((90, 0), False, False, True, False, True)])
        self.assertEqual(out, [None, None, None, None])
    def test_mode_switches_midway_and_stays_when_keys_are_released(self):
        out = self.feed([((0, 0), True, True, True, False, False), ((30, 0), True, True, True, False, False), ((31, 0), True, True, True, True, False), ((32, 0), True, False, True, False, False), ((33, 0), True, False, True, False, False), ((34, 0), True, True, True, False, True), ((34, 0), False, False, True, False, False)])
        self.assertEqual(out, [None, ('engage', 'convert'), ('mode', 'tools'), None, None, ('mode', 'actions'), ('release', None)])
    def test_click_without_movement_never_engages(self):
        self.assertEqual(self.feed([((0, 0), True, True, True, False, False), ((3, 3), True, True, True, False, False), ((3, 3), False, True, True, False, False)]), [None, None, None])
    def test_wrong_source_is_ignored_until_release(self):
        out = self.feed([((0, 0), True, True, False, False, False), ((50, 0), True, True, True, False, False), ((90, 0), True, True, True, False, False), ((90, 0), False, True, True, False, False), ((0, 0), True, True, True, False, False), ((60, 0), True, True, True, False, False)])
        self.assertEqual(out, [None, None, None, None, None, ('engage', 'convert')])
    def test_no_release_event_if_never_engaged(self):
        self.assertIsNone(self.feed([((0, 0), True, False, True, False, False), ((50, 0), True, False, True, False, False), ((50, 0), False, False, True, False, False)])[-1])

class OverlayBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.dir = Path(self.tmp.name).resolve();self.png = self.dir / 'a.png';Image.new('RGB', (8, 8)).save(self.png);self.overlay = WheelOverlay();self.mime = QMimeData()
    def tearDown(self): self.overlay.dismiss();self.tmp.cleanup()
    def urls(self, *paths): self.mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    def enter(self, offered=Qt.MoveAction | Qt.CopyAction):
        e = QDragEnterEvent(QPoint(210, 210), offered, self.mime, Qt.LeftButton, Qt.ShiftModifier);e.setDropAction(Qt.MoveAction);self.overlay.dragEnterEvent(e);return e
    def drop_at(self, pos, offered=Qt.MoveAction | Qt.CopyAction):
        e = QDropEvent(QPointF(*pos), offered, self.mime, Qt.LeftButton, Qt.ShiftModifier);e.setDropAction(Qt.MoveAction);self.overlay.dropEvent(e);return e
    def move_to(self, pos):
        m = QDragMoveEvent(QPoint(*map(int, pos)), Qt.MoveAction | Qt.CopyAction, self.mime, Qt.LeftButton, Qt.ShiftModifier);m.setDropAction(Qt.MoveAction);self.overlay.dragMoveEvent(m);return m
    def centre_of(self, index):
        n = len(self.overlay.items);mid = math.radians(90 - (index + .5) * 360 / n);r = (self.overlay.OUTER + self.overlay.INNER) / 2;c = self.overlay.SIZE / 2
        return (c + r * math.cos(mid), c - r * math.sin(mid))
    def tab_centre(self, mode):
        c = self.overlay.tab_rects()[MODES.index(mode)].center();return (c.x(), c.y())

class OverlayTests(OverlayBase):
    def test_enter_answers_copy_never_move(self):
        self.urls(self.png);e = self.enter();self.assertTrue(e.isAccepted());self.assertEqual(e.dropAction(), Qt.CopyAction)
        self.assertEqual(self.move_to((210, 210)).dropAction(), Qt.CopyAction)
    def test_copy_only_in_every_mode(self):
        self.urls(self.png);self.enter()
        for mode in MODES:
            self.overlay.set_mode(mode);self.assertEqual(self.move_to((210, 210)).dropAction(), Qt.CopyAction, mode)
    def test_refuses_when_copy_is_not_offered(self):
        self.urls(self.png);self.assertFalse(self.enter(Qt.MoveAction).isAccepted());self.assertEqual(self.overlay.paths, [])
    def test_ignores_remote_urls_and_folders(self):
        self.mime.setUrls([QUrl('https://example.com/x.png')]);self.assertFalse(self.enter().isAccepted())
        self.urls(self.dir);self.assertFalse(self.enter().isAccepted())
        self.mime.setText('hello');self.mime.setUrls([]);self.assertFalse(self.enter().isAccepted())
    def test_drop_on_tile_emits_kind_and_key_with_copy(self):
        self.urls(self.png);self.enter();got = [];self.overlay.chosen.connect(lambda paths, kind, key: got.append((paths, kind, key)))
        e = self.drop_at(self.centre_of(1));self.assertEqual(e.dropAction(), Qt.CopyAction)
        self.assertEqual(len(got), 1);self.assertEqual(got[0][1:], ('convert', 'JPEG'));self.assertEqual(Path(got[0][0][0]), self.png)
    def test_drop_in_centre_outside_or_on_a_tab_is_ignored(self):
        self.urls(self.png);self.enter();got = [];self.overlay.chosen.connect(lambda *a: got.append(a))
        for pos in ((self.overlay.SIZE // 2, self.overlay.SIZE // 2), (5, 5), self.tab_centre('tools')):
            self.enter();e = self.drop_at(pos);self.assertFalse(e.isAccepted())
        self.assertEqual(got, [])
    def test_hover_tracks_segment_and_geometry(self):
        self.urls(self.png);self.enter();o = self.overlay
        self.assertEqual(o.segment_at(QPoint(*map(int, self.centre_of(0)))), 0);self.assertEqual(o.segment_at(QPoint(*map(int, self.centre_of(len(o.items) - 1)))), len(o.items) - 1)
        self.assertEqual(o.segment_at(QPoint(o.SIZE // 2, o.SIZE // 2)), -1);self.assertEqual(o.segment_at(QPoint(0, 0)), -1)
        self.move_to(self.centre_of(2));self.assertEqual(o.hover, 2)
    def test_present_stays_on_screen_and_renders(self):
        self.urls(self.png);self.enter();self.overlay.present(QPoint(0, 0));self.assertTrue(self.overlay.isVisible())
        screen = self.overlay.screen().availableGeometry();self.assertTrue(screen.contains(self.overlay.geometry().topLeft()));self.assertFalse(self.overlay.grab().isNull())
    def test_release_hides_after_grace_period(self):
        self.overlay.present(QPoint(300, 300));self.overlay.dismiss_soon();self.assertTrue(self.overlay.isVisible());pump(self.app, .9);self.assertFalse(self.overlay.isVisible())

class ModeTabTests(OverlayBase):
    def test_hovering_a_tab_while_dragging_switches_mode(self):
        self.urls(self.png);self.enter();seen = [];self.overlay.mode_changed.connect(seen.append)
        self.move_to(self.tab_centre('tools'));self.assertEqual(self.overlay.mode, 'tools');self.assertIn('crop_image', [i.key for i in self.overlay.items])
        self.move_to(self.tab_centre('actions'));self.assertEqual(self.overlay.mode, 'actions');self.assertEqual(len(self.overlay.items), 5)
        self.move_to(self.tab_centre('convert'));self.assertEqual(self.overlay.mode, 'convert');self.assertEqual(seen, ['tools', 'actions', 'convert'])
    def test_drop_on_tool_and_action_tiles(self):
        self.urls(self.png);self.enter();got = []
        self.overlay.chosen.connect(lambda paths, kind, key: got.append((kind, key)))
        self.overlay.set_mode('tools');self.drop_at(self.centre_of(0));self.enter();self.overlay.set_mode('actions');self.drop_at(self.centre_of(2))
        self.assertEqual(got, [('tool', 'compress'), ('action', 'copy_paths')])
    def test_empty_modes_explain_themselves(self):
        pdf = self.dir / 'a.pdf';pdf.write_bytes(b'%PDF');self.urls(self.png, pdf);self.enter();self.overlay.set_mode('tools');self.assertEqual(self.overlay.items, []);self.assertFalse(self.overlay.grab().isNull())
    def test_twelve_tiles_shrink_to_fit_and_one_tile_works(self):
        o = self.overlay;self.assertEqual(o.tile_size(8), o.TILE);self.assertLess(o.tile_size(12), o.TILE);self.assertGreater(o.tile_size(12), o.TILE * .7)
        self.urls(self.png);self.enter();o.items = o.items[:1];self.assertEqual(o.segment_at(QPoint(int(o.SIZE / 2), int(o.SIZE / 2 + 140))), 0);self.assertEqual(o.segment_at(QPoint(int(o.SIZE / 2), int(o.SIZE / 2 - 140))), 0);self.assertFalse(o.grab().isNull())
    def test_picker_click_flow(self):
        got = [];self.overlay.chosen.connect(lambda paths, kind, key: got.append((paths, kind, key)))
        self.overlay.present(QPoint(400, 400), 'convert', [str(self.png)], interactive=True);self.assertTrue(self.overlay.interactive)
        QTest.mouseClick(self.overlay, Qt.LeftButton, Qt.NoModifier, QPoint(*map(int, self.tab_centre('tools'))));self.assertEqual(self.overlay.mode, 'tools')
        expected = self.overlay.items[2].key;QTest.mouseClick(self.overlay, Qt.LeftButton, Qt.NoModifier, QPoint(*map(int, self.centre_of(2))))
        self.assertEqual(got, [([str(self.png)], 'tool', expected)]);self.assertFalse(self.overlay.isVisible())
    def test_picker_escape_and_outside_click_dismiss(self):
        self.overlay.present(QPoint(400, 400), 'convert', [str(self.png)], interactive=True);QTest.keyClick(self.overlay, Qt.Key_Escape);self.assertFalse(self.overlay.isVisible())
        self.overlay.present(QPoint(400, 400), 'convert', [str(self.png)], interactive=True);QTest.mouseClick(self.overlay, Qt.LeftButton, Qt.NoModifier, QPoint(4, 4));self.assertFalse(self.overlay.isVisible())
    def at_radius(self, index, r):
        n = len(self.overlay.items);mid = math.radians(90 - (index + .5) * 360 / n);c = self.overlay.SIZE / 2
        return (c + r * math.cos(mid), c - r * math.sin(mid))
    def test_pdf_tile_splits_into_separate_and_one_file_while_dragging_several(self):
        b = self.dir / 'b.png';Image.new('RGB', (8, 8)).save(b);self.urls(self.png, b);self.enter();o = self.overlay
        got = [];o.chosen.connect(lambda paths, kind, key: got.append(key));i = [x.key for x in o.items].index('Image → PDF');outer, inner = o.OUTER - 12, o.INNER + 16
        self.move_to(self.at_radius(i, outer));self.assertEqual((o.hover, o.hover_part), (i, 'one'));self.assertIn('One file', o.accessibleDescription());self.assertFalse(o.grab().isNull())
        self.move_to(self.at_radius(i, inner));self.assertEqual(o.hover_part, 'separate');self.assertFalse(o.grab().isNull())
        j = [x.key for x in o.items].index('JPEG');self.assertTrue(o.splits(i));self.assertFalse(o.splits(j))
        self.drop_at(self.at_radius(i, outer));self.enter();self.drop_at(self.at_radius(i, inner));self.enter();self.drop_at(self.at_radius(j, outer))
        self.assertEqual(got, ['Combine → PDF', 'Image → PDF', 'JPEG'])
    def test_single_file_tiles_never_split(self):
        self.urls(self.png);self.enter();o = self.overlay;i = [x.key for x in o.items].index('Image → PDF');got = [];o.chosen.connect(lambda paths, kind, key: got.append(key))
        self.move_to(self.at_radius(i, o.OUTER - 12));self.assertIsNone(o.hover_part);self.drop_at(self.at_radius(i, o.OUTER - 12));self.assertEqual(got, ['Image → PDF'])
    def test_non_interactive_wheel_ignores_stray_clicks(self):
        got = [];self.overlay.chosen.connect(lambda *a: got.append(a));self.overlay.present(QPoint(400, 400));QTest.mouseClick(self.overlay, Qt.LeftButton, Qt.NoModifier, QPoint(240, 100));self.assertEqual(got, []);self.assertTrue(self.overlay.isVisible())

class WatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def test_signals_from_sampler(self):
        script = iter([Sample((0, 0), True, False, True, True), Sample((50, 0), True, False, True, True), Sample((60, 0), True, True, True, False, True), Sample((60, 0), False, False, True)])
        w = DragWatcher(sampler=lambda was: next(script), interval=1);events = []
        w.engaged.connect(lambda p, m: events.append(('engage', m)));w.mode_changed.connect(lambda m: events.append(('mode', m)));w.released.connect(lambda: events.append(('release', None)))
        for _ in range(4): w.tick()
        self.assertEqual(events, [('engage', 'tools'), ('mode', 'actions'), ('release', None)])

class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.dir = Path(self.tmp.name).resolve();self.settings = QSettings(str(self.dir / 's.ini'), QSettings.IniFormat);self.c = WheelController(self.settings)
    def tearDown(self): self.c.shutdown();self.tmp.cleanup()
    def wait(self, timeout=60):
        end = time.monotonic() + timeout
        while self.c.batch.isRunning() or not self.c.statuses:
            self.assertLess(time.monotonic(), end);pump(self.app, .02)
        pump(self.app, .05)
    def wait_action(self, timeout=30):
        end = time.monotonic() + timeout
        while self.c.action_worker.isRunning(): self.assertLess(time.monotonic(), end);pump(self.app, .02)
        pump(self.app, .05)
    def test_wheel_conversion_saves_beside_original_and_shows_success(self):
        src = self.dir / 'photo.png';Image.new('RGB', (16, 16), 'orange').save(src)
        self.c.dispatch([str(src)], 'convert', 'JPEG');self.assertEqual(self.c.notch.kind, 'info');self.wait()
        self.assertEqual(self.c.notch.kind, 'ok');self.assertTrue((self.dir / 'photo-converted.jpg').is_file());self.assertTrue(src.is_file())
    def test_one_file_choice_from_the_wheel_saves_one_pdf(self):
        a, b = self.dir / 'a.png', self.dir / 'b.png'
        for f in (a, b): Image.new('RGB', (16, 16), 'orange').save(f)
        self.c.dispatch([str(a), str(b)], 'convert', 'Combine → PDF');self.wait()
        self.assertEqual(self.c.notch.kind, 'ok');self.assertEqual(self.c.notch.text, 'Combined PDF saved');self.assertEqual([f.name for f in self.dir.glob('*.pdf')], ['combined.pdf'])
    def test_failure_is_reported_in_notch_without_losing_good_files(self):
        good = self.dir / 'good.png';Image.new('RGB', (16, 16)).save(good);bad = self.dir / 'bad.png';bad.write_bytes(b'broken')
        self.c.convert([str(bad), str(good)], 'JPEG');self.wait()
        self.assertEqual(self.c.notch.kind, 'error');self.assertIn('1 converted', self.c.notch.text);self.assertTrue((self.dir / 'good-converted.jpg').is_file())
    def test_missing_tool_message(self):
        # A chosen LibreOffice that does not exist, so the result does not depend on one being installed on this machine.
        doc = self.dir / 'a.docx';doc.write_bytes(b'x');self.settings.setValue('soffice', str(self.dir / 'missing' / 'soffice.exe'))
        self.c.convert([str(doc)], 'Office → PDF');self.wait()
        self.assertEqual(self.c.notch.kind, 'error');self.assertIn('LibreOffice', self.c.notch.detail)
    def test_notch_slides_in_stays_long_enough_and_retracts(self):
        # A short `seconds` is only a minimum: the card stays at least its reading time, then slides away.
        n = self.c.notch;n.show_message('Converted 1 file', 'ok', seconds=.8);self.assertTrue(n.isVisible());self.assertGreaterEqual(n.total, Notch.MIN_SECONDS['ok'])
        pump(self.app, 1.2);self.assertTrue(n.isVisible());self.assertEqual(n.pos(), n.anchor())
        n.left = .05;pump(self.app, .6);self.assertFalse(n.isVisible());self.assertFalse(n.grab().isNull())
    def test_card_shows_long_text_in_full_and_grows(self):
        n = self.c.notch;n.show_message('Converted', 'ok', detail='one file');short = n.H
        # Far longer than one line (the old card showed about 58 characters), including a path with no spaces to break at.
        long = 'LibreOffice could not convert this file; it may be damaged. ' + r'C:\Docs\quarterly-report-final-2026.docx'
        n.show_message("Couldn't convert", 'error', detail=long);self.assertGreater(n.H, short)
        self.assertEqual(''.join(n.lines[1]).replace(' ', ''), long.replace(' ', ''))          # every character is on the card, none elided
        self.assertGreaterEqual(n.total, Notch.MIN_SECONDS['error']);n.retract()
    def test_hover_pauses_countdown_and_buttons_work(self):
        n = self.c.notch;n.show_message('1 converted · 1 failed', 'error', folder=str(self.dir), detail='bad file');n.left = 1.0
        n.enterEvent(None);pump(self.app, .5);self.assertAlmostEqual(n.left, 1.0, places=2);n.leaveEvent(None);self.assertGreaterEqual(n.left, 2.5)
        copy = n.rects['button:copy'].center() + QPointF(n.M, n.M);n.mousePressEvent(mock.Mock(position=lambda: copy))
        self.assertEqual(QApplication.clipboard().text(), '1 converted · 1 failed\nbad file');self.assertTrue(n.copied)
        close = n.rects['close'].center() + QPointF(n.M, n.M);n.mousePressEvent(mock.Mock(position=lambda: close));pump(self.app, .5);self.assertFalse(n.isVisible())
    def test_wheel_and_card_have_accessible_text(self):
        n = self.c.notch;n.show_message('Converting to JPEG', 'info', detail='1 of 2 done', fraction=.5)
        self.assertEqual(n.accessibleName(), 'Open Tangerine progress');self.assertEqual(n.accessibleDescription(), 'Converting to JPEG. 1 of 2 done 50%');n.hide()
        o = self.c.overlay;self.assertEqual(o.accessibleName(), 'Open Tangerine drag wheel')
        o.present(QPoint(300, 300), 'convert', [str(self.dir / 'a.png')]);o.set_hover(0);self.assertEqual(o.accessibleDescription(), 'Convert: ' + o.items[0].label);o.dismiss()
    def test_card_position_follows_setting(self):
        n = self.c.notch;g = (QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()).availableGeometry()
        for position in ('top-left', 'top-center', 'top-right', 'bottom-left', 'bottom-right'):
            self.settings.setValue('card/position', position);n.hide();n.show_message('Working', 'info');a = n.anchor()
            card_left, card_top = a.x() + n.M, a.y() + n.M
            self.assertTrue(g.contains(card_left, card_top) and g.contains(card_left + n.W - 1, card_top + n.H - 1), position)
            if position.endswith('left'): self.assertLess(card_left - g.left(), 40)
            if position.endswith('right'): self.assertLess(g.right() - (card_left + n.W), 40)
            if position.startswith('bottom'): self.assertLess(g.bottom() - (card_top + n.H), 40)
            else: self.assertLess(card_top - g.top(), 40)
        n.hide()
    def test_enable_setting_persists(self):
        self.assertFalse(self.c.enabled, 'off until turned on');self.c.set_enabled(True);self.assertTrue(WheelController(self.settings).enabled)
        self.c.set_enabled(False);self.assertFalse(WheelController(self.settings).enabled)
    def test_wheel_uses_the_saved_theme_each_time_it_opens(self):
        self.c.engage(QPoint(300, 300), 'convert');self.assertEqual(self.c.overlay.look, 'light');self.assertFalse(self.c.overlay.grab().isNull())
        self.settings.setValue('wheel/theme', 'dark');self.c.engage(QPoint(300, 300), 'tools');self.assertEqual(self.c.overlay.look, 'dark');self.assertFalse(self.c.overlay.grab().isNull())
        self.c.overlay.dismiss()
    def test_copy_paths_and_copy_files_actions(self):
        a = self.dir / 'one.txt';a.write_text('1');b = self.dir / 'two.txt';b.write_text('2')
        self.c.dispatch([str(a), str(b)], 'action', 'copy_paths');self.assertEqual(QApplication.clipboard().text().splitlines(), [str(a), str(b)]);self.assertEqual(self.c.notch.kind, 'ok')
        self.c.dispatch([str(a), str(b)], 'action', 'copy_files');mime = QApplication.clipboard().mimeData();self.assertEqual([Path(u.toLocalFile()) for u in mime.urls()], [a, b])
        self.assertEqual(int.from_bytes(bytes(mime.data('application/x-qt-windows-mime;value="Preferred DropEffect"')), 'little'), 1)
    def test_duplicate_never_overwrites(self):
        a = self.dir / 'report.txt';a.write_text('original')
        for expected in ('report - copy.txt', 'report - copy 2.txt', 'report - copy 3.txt'):
            self.c.dispatch([str(a)], 'action', 'duplicate');self.wait_action();self.assertTrue((self.dir / expected).is_file(), expected)
        self.assertEqual(a.read_text(), 'original');self.assertEqual(self.c.notch.kind, 'ok')
    def test_hash_action_puts_checksums_on_clipboard(self):
        import hashlib
        a = self.dir / 'h.bin';a.write_bytes(b'tangerine');self.c.dispatch([str(a)], 'action', 'hash');self.wait_action()
        self.assertEqual(QApplication.clipboard().text(), hashlib.sha256(b'tangerine').hexdigest() + '  h.bin')
    def test_action_errors_are_shown(self):
        self.c.dispatch([str(self.dir / 'missing.txt')], 'action', 'hash');self.wait_action();self.assertEqual(self.c.notch.kind, 'error')
    def test_reveal_uses_the_shell_and_falls_back_to_explorer(self):
        import unittest.mock as mock
        with mock.patch.object(actions, 'select_in_explorer', return_value=True) as sel, mock.patch.object(actions.subprocess, 'Popen') as popen:
            self.c.dispatch([str(self.dir / 'a.txt'), str(self.dir / 'b.txt')], 'action', 'reveal');sel.assert_called_once();popen.assert_not_called()
        with mock.patch.object(actions, 'select_in_explorer', return_value=False), mock.patch.object(actions.subprocess, 'Popen') as popen:
            self.c.dispatch([str(self.dir / 'a.txt')], 'action', 'reveal');popen.assert_called_once()
    def test_tool_dispatch_opens_a_tool_window(self):
        src = self.dir / 'p.png';Image.new('RGB', (30, 20)).save(src);self.c.dispatch([str(src)], 'tool', 'rotate_image');self.assertEqual(len(self.c.tool_windows), 1);w = self.c.tool_windows[0]
        self.assertEqual(w.tool.id, 'rotate_image');w.close();self.assertEqual(len(self.c.tool_windows), 0)
    def test_pick_files_shows_interactive_wheel_in_the_requested_mode(self):
        src = self.dir / 'p.png';Image.new('RGB', (8, 8)).save(src);self.c.pick_files('tools', [str(src)]);o = self.c.overlay
        self.assertTrue(o.isVisible() and o.interactive);self.assertEqual(o.mode, 'tools');self.assertIn('crop_image', [i.key for i in o.items]);o.dismiss()

@unittest.skipUnless(sys.platform == 'win32', 'Windows sampler')
class WindowsSamplerTests(unittest.TestCase):
    def test_sampler_reads_state_without_error(self):
        s = wheel.WindowsSampler()(False);self.assertIsInstance(s.pos, tuple);self.assertIsInstance(s.left, bool);self.assertIsInstance(s.alt, bool);self.assertIsInstance(s.ctrl, bool)
    def test_reveal_signatures_survive_a_missing_path(self):
        # Exercises the ctypes calls against a path that does not exist; no Explorer window can open.
        self.assertFalse(actions.select_in_explorer(r'C:\definitely\missing\folder', [r'C:\definitely\missing\folder\x.txt']))

if __name__ == '__main__': unittest.main()
