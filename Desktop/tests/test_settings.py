"""Phase 5: saved preferences (output folder, excluded applications), the wheel's exclusion check and the Settings window."""
import os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
import prefs, settings_dialog

class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name).resolve();self.settings = QSettings(str(self.root / 'test.ini'), QSettings.IniFormat)
    def tearDown(self): self.settings.sync();self.tmp.cleanup()

class OutputFolder(Base):
    def test_default_is_next_to_the_original(self):
        self.assertEqual(prefs.output_mode(self.settings), 'beside');self.assertEqual(prefs.output_folder(self.settings), '');self.assertFalse(prefs.reveal_results(self.settings))
    def test_custom_folder_is_used_when_it_exists(self):
        out = self.root / 'results';out.mkdir();self.settings.setValue('output/mode', 'custom');self.settings.setValue('output/folder', str(out));self.assertEqual(prefs.output_folder(self.settings), str(out))
    def test_missing_custom_folder_falls_back_to_beside_original(self):
        self.settings.setValue('output/mode', 'custom');self.settings.setValue('output/folder', str(self.root / 'gone'));self.assertEqual(prefs.output_folder(self.settings), '')
        self.settings.setValue('output/folder', 'relative/dir');self.assertEqual(prefs.output_folder(self.settings), '')       # the engine only takes absolute folders
    def test_downloads_and_desktop_resolve_to_real_folders(self):
        for mode in ('downloads', 'desktop'):
            self.settings.setValue('output/mode', mode);folder = prefs.output_folder(self.settings)
            self.assertTrue(folder == '' or Path(folder).is_dir(), mode)
    def test_unknown_mode_is_ignored(self):
        self.settings.setValue('output/mode', 'nowhere');self.assertEqual(prefs.output_mode(self.settings), 'beside')
    def test_the_engine_accepts_the_folder_it_is_given(self):
        import engine
        out = self.root / 'results';out.mkdir();self.settings.setValue('output/mode', 'custom');self.settings.setValue('output/folder', str(out))
        src = self.root / 'a.png'
        from PIL import Image
        Image.new('RGB', (8, 8)).save(src);result = engine.convert({'paths': [str(src)], 'target': 'JPEG', 'output': prefs.output_folder(self.settings)});self.assertEqual(Path(result[0]).parent, out)

class Exclusions(Base):
    def test_round_trip_and_case_and_path_forms(self):
        self.assertEqual(prefs.add_excluded(self.settings, 'C:\\Program Files\\Corel\\CorelDRAW.EXE'), 'coreldraw.exe')
        self.assertEqual(prefs.excluded(self.settings), {'coreldraw.exe': 'CorelDRAW'});self.assertIn('coreldraw.exe', prefs.excluded_names(self.settings))
        prefs.remove_excluded(self.settings, 'CorelDRAW.exe');self.assertEqual(prefs.excluded(self.settings), {})
    def test_only_programs_can_be_excluded(self):
        self.assertIsNone(prefs.add_excluded(self.settings, 'C:\\notes.txt'));self.assertEqual(prefs.excluded(self.settings), {})
    def test_matching_ignores_case_and_folder(self):
        names = frozenset({'coreldrw.exe'})
        self.assertTrue(prefs.is_excluded('C:\\Apps\\CorelDRW.EXE', names));self.assertTrue(prefs.is_excluded('/opt/x/coreldrw.exe', names))
        self.assertFalse(prefs.is_excluded('C:\\Windows\\explorer.exe', names));self.assertFalse(prefs.is_excluded('', names));self.assertFalse(prefs.is_excluded(None, names))
    def test_damaged_value_gives_an_empty_list(self):
        for bad in ('not json', '[1,2]', '{"": "x"}'): self.settings.setValue('wheel/excluded', bad);self.assertEqual(prefs.excluded(self.settings), {}, bad)

@unittest.skipUnless(sys.platform == 'win32', 'The wheel sampler is Windows-only')
class WheelCheck(Base):
    def sampler(self, **kw):
        import wheel
        return wheel.WindowsSampler(**kw)
    def test_excluded_program_never_starts_the_wheel(self):
        s = self.sampler(excluded=lambda: frozenset({'coreldrw.exe'}))
        self.assertFalse(s.allowed(4242, 'CabinetWClass', 'C:\\Corel\\CorelDRW.exe'))          # even from a class that is normally allowed
        self.assertTrue(s.allowed(4242, 'CabinetWClass', 'C:\\Windows\\explorer.exe'))
    def test_other_windows_are_still_limited_to_explorer_unless_any_app_is_on(self):
        s = self.sampler()
        self.assertFalse(s.allowed(4242, 'Notepad', 'C:\\Windows\\notepad.exe'));s.any_app = True;self.assertTrue(s.allowed(4242, 'Notepad', 'C:\\Windows\\notepad.exe'))
    def test_exclusion_beats_trigger_from_other_apps(self):
        s = self.sampler(any_app=True, excluded=lambda: frozenset({'notepad.exe'}));self.assertFalse(s.allowed(4242, 'Notepad', 'C:\\Windows\\notepad.exe'))
    def test_own_windows_never_start_the_wheel(self):
        self.assertFalse(self.sampler(any_app=True).allowed(os.getpid(), 'Qt', 'C:\\x\\python.exe'))
    def test_list_is_read_live_from_settings(self):
        names = lambda: prefs.excluded_names(self.settings);s = self.sampler(any_app=True, excluded=names);self.assertTrue(s.allowed(1, 'X', 'C:\\a\\tool.exe'))
        prefs.add_excluded(self.settings, 'C:\\a\\tool.exe');self.assertFalse(s.allowed(1, 'X', 'C:\\a\\tool.exe'))          # no restart needed
    def test_image_of_finds_this_program_and_survives_a_bad_pid(self):
        s = self.sampler();self.assertEqual(Path(s.image_of(os.getpid())).name.lower(), Path(sys.executable).name.lower());self.assertEqual(s.image_of(0xFFFFFFF0), '')

class Health(unittest.TestCase):
    def test_a_working_helper_reports_its_version(self):
        state, text = settings_dialog.helper_health(sys.executable, ['--version']);self.assertEqual(state, 'ready');self.assertIn('Python', text)
    def test_a_helper_that_fails_is_broken(self):
        state, text = settings_dialog.helper_health(sys.executable, ['-c', 'import sys;print("no codec", file=sys.stderr);sys.exit(3)']);self.assertEqual((state, text), ('broken', 'no codec'))
    def test_a_missing_or_hanging_helper_is_broken_not_an_exception(self):
        self.assertEqual(settings_dialog.helper_health(str(Path(tempfile.gettempdir()) / 'no-such-helper.exe'), ['-version'])[0], 'broken')
        state, text = settings_dialog.helper_health(sys.executable, ['-c', 'import time;time.sleep(30)'], timeout=1);self.assertEqual(state, 'broken');self.assertIn('did not answer', text)
    def test_libreoffice_is_asked_through_its_console_twin_on_windows(self):
        folder = Path(tempfile.mkdtemp());exe = folder / 'soffice.exe';exe.write_bytes(b'')
        self.assertEqual(settings_dialog.probe_path('soffice', str(exe)), str(exe))                                   # no soffice.com: unchanged
        (folder / 'soffice.com').write_bytes(b'')
        self.assertEqual(settings_dialog.probe_path('soffice', str(exe)), str(folder / 'soffice.com') if os.name == 'nt' else str(exe))
        self.assertEqual(settings_dialog.probe_path('ffmpeg', str(exe)), str(exe))

class Window(Base):
    def open(self, **kw):
        with mock.patch.object(settings_dialog, 'helper_health', return_value=('ready', 'ffmpeg version 7.1')):
            return settings_dialog.SettingsDialog(self.settings, **kw)
    def test_has_the_three_pages_and_opens_on_the_requested_one(self):
        d = self.open(tab='formats');self.assertEqual([d.sidebar.item(i).text() for i in range(d.sidebar.count())], ['General', 'Formats', 'About']);self.assertEqual(d.title.text(), 'Formats');self.assertEqual(d.stack.currentIndex(), 1);d.done(0)
    def test_unknown_tab_opens_general(self):
        d = self.open(tab='nope');self.assertEqual(d.title.text(), 'General');d.done(0)
    def test_output_choices_persist(self):
        d = self.open();d.mode.setCurrentIndex(d.mode.findData('custom'));self.assertTrue(d.custom_row.isVisibleTo(d));self.assertEqual(self.settings.value('output/mode'), 'custom')
        out = self.root / 'r';out.mkdir()
        with mock.patch.object(settings_dialog.QFileDialog, 'getExistingDirectory', return_value=str(out)): d.choose_folder()
        d.reveal.setChecked(True);self.assertEqual(prefs.output_folder(self.settings), str(out));self.assertTrue(prefs.reveal_results(self.settings));self.assertIn(str(out), d.custom_label.text());d.done(0)
        again = self.open();self.assertEqual(again.mode.currentData(), 'custom');self.assertTrue(again.reveal.isChecked());again.done(0)
    def test_excluded_list_add_and_remove(self):
        d = self.open()
        with mock.patch.object(settings_dialog.QFileDialog, 'getOpenFileNames', return_value=(['C:/Apps/CorelDRW.exe', 'C:/Apps/readme.txt'], '')): d.add_excluded()
        self.assertEqual(d.excluded.count(), 1);self.assertIn('coreldrw.exe', prefs.excluded(self.settings));self.assertFalse(d.remove_excluded.isEnabled())
        d.excluded.setCurrentRow(0);self.assertTrue(d.remove_excluded.isEnabled());d.remove_selected_excluded();self.assertEqual(d.excluded.count(), 0);self.assertEqual(prefs.excluded(self.settings), {});d.done(0)
    def test_formats_page_shows_helper_state(self):
        fake = {'ffmpeg': (r'C:\f\ffmpeg.exe', 'detected'), 'tesseract': ('', ''), 'soffice': (r'C:\o\soffice.exe', 'chosen')}
        with mock.patch.object(settings_dialog, 'helper_state', side_effect=lambda s, k: fake[k]), mock.patch.object(settings_dialog, 'helper_health', side_effect=lambda p, a, timeout=8: ('broken', 'bad dll') if 'soffice' in p else ('ready', 'ffmpeg version 7.1')):
            d = settings_dialog.SettingsDialog(self.settings, tab='formats')
            for c in list(d.checks): c.wait(5000)
            self.app.processEvents();status = {k: v[0].text() for k, v in d.rows.items()}
            self.assertIn('Ready', status['ffmpeg']);self.assertIn('ffmpeg version 7.1', status['ffmpeg']);self.assertIn('Not found', status['tesseract']);self.assertIn('Cannot run', status['soffice']);self.assertIn('bad dll', status['soffice'])
            self.assertTrue(d.rows['ffmpeg'][1].isHidden());self.assertFalse(d.rows['soffice'][1].isHidden());d.done(0)       # "Use automatic" only where a file was chosen
    def test_closing_while_a_check_runs_waits_for_it(self):
        import time
        def slow(path, args, timeout=8): time.sleep(.3);return 'ready', 'v1'
        with mock.patch.object(settings_dialog, 'helper_state', return_value=(sys.executable, 'detected')), mock.patch.object(settings_dialog, 'helper_health', side_effect=slow):
            d = settings_dialog.SettingsDialog(self.settings);d.done(0)
            self.assertFalse(any(c.isRunning() for c in d.checks))
    @unittest.skipUnless(sys.platform == 'win32', 'The wheel is Windows-only')
    def test_wheel_section_needs_a_controller_and_drives_it(self):
        self.assertFalse(hasattr(self.open(), 'wheel_on'))
        class Fake:
            enabled = True;calls = []
            def set_enabled(self, on): self.calls.append(('enabled', on))
            def set_any_app(self, on): self.calls.append(('any', on))
            def refresh_menu(self): self.calls.append('menu')
        fake = Fake();d = self.open(controller=fake);d.wheel_on.setChecked(False);d.any_app.setChecked(True);d.done(0)
        self.assertEqual(fake.calls, [('enabled', False), ('any', True), 'menu'])
    def test_wheel_theme_is_saved_on_every_platform(self):
        # No drag-wheel controller (as on Linux): the theme still applies to the in-window glass wheel.
        self.assertEqual(prefs.wheel_theme(self.settings), 'light')
        d = self.open();self.assertEqual(d.wheel_theme.currentData(), 'light');d.wheel_theme.setCurrentIndex(d.wheel_theme.findData('dark'));d.done(0)
        self.assertEqual(prefs.wheel_theme(self.settings), 'dark');self.assertEqual(self.open().wheel_theme.currentData(), 'dark')
        self.settings.setValue('wheel/theme', 'neon');self.assertEqual(prefs.wheel_theme(self.settings), 'light')
    def test_main_window_uses_the_saved_output_folder(self):
        from app import Window as Main
        out = self.root / 'r';out.mkdir();self.settings.setValue('output/mode', 'custom');self.settings.setValue('output/folder', str(out))
        w = Main();w.settings = self.settings;w.update_folder_label();self.assertIn(str(out), w.where.text());self.assertFalse(w.folder_reset.isVisible())
        src = self.root / 'a.png'
        from PIL import Image
        Image.new('RGB', (8, 8)).save(src);w.add_paths([str(src)]);w.target.setCurrentText('PNG');w.start();options = w.batch.options;w.batch.wait(20000);self.app.processEvents();w.close()
        self.assertEqual(options['output'], str(out));self.assertTrue((out / 'a-converted.png').is_file())

if __name__ == '__main__': unittest.main()
