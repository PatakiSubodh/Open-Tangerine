"""Worker memory cap: a Windows job object per worker (winjob.py, runner.run_job) and the shared out-of-memory message."""
import contextlib, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine, runner, winjob
from engine import MEMORY_MESSAGE
from PIL import Image

WIN = os.name == 'nt'
OK = '{"ok":true,"outputs":[]}'
MiB = 1024 * 1024

def child(code): return [sys.executable, '-c', 'import sys;sys.stdin.read();' + code]     # waits for the request, as the real worker does

class WorkerMessage(unittest.TestCase):
    def run_worker(self, error):
        stdin = io.TextIOWrapper(io.BytesIO(b'{}'));out = io.StringIO()
        with mock.patch.object(engine, 'convert', side_effect=error), mock.patch.object(sys, 'stdin', stdin), contextlib.redirect_stdout(out): code = engine.worker_main()
        return code, json.loads(out.getvalue())
    def test_memory_error_becomes_a_clear_message(self):
        code, result = self.run_worker(MemoryError());self.assertEqual(code, 1);self.assertEqual(result, {'ok': False, 'error': MEMORY_MESSAGE})
    def test_other_errors_keep_their_text(self):
        code, result = self.run_worker(engine.ConversionError('Bad file.'));self.assertEqual(result['error'], 'Bad file.')

class NotWindows(unittest.TestCase):
    def test_job_is_only_created_on_windows(self):
        self.assertIsNone(winjob.MemoryJob.create(0));self.assertEqual(winjob.MemoryJob.create(1 << 30) is not None, WIN)

@unittest.skipUnless(WIN, 'Windows job objects')
class Cap(unittest.TestCase):
    def test_runaway_allocation_is_stopped_with_a_clear_message(self):
        info = {}
        with self.assertRaisesRegex(ValueError, 'more memory than a conversion is allowed'): runner.run_job({}, command=child(f'b=bytearray({700 * MiB});print({OK!r})'), memory_limit=300 * MiB, info=info)
        self.assertTrue(info['capped'])
    def test_same_allocation_is_fine_under_a_bigger_limit_and_the_peak_is_reported(self):
        info = {};self.assertEqual(runner.run_job({}, command=child(f'b=bytearray({200 * MiB});print({OK!r})'), memory_limit=1024 * MiB, info=info), [])
        self.assertTrue(info['capped']);self.assertGreater(info['peak_memory'], 180 * MiB);self.assertLess(info['peak_memory'], 600 * MiB)
    def test_no_limit_means_no_job(self):
        info = {};runner.run_job({}, command=child(f'print({OK!r})'), memory_limit=0, info=info);self.assertEqual(info, {'capped': False, 'peak_memory': 0})
    def test_if_the_job_cannot_be_created_the_job_still_runs(self):
        info = {}
        with mock.patch.object(winjob.MemoryJob, 'create', return_value=None): self.assertEqual(runner.run_job({}, command=child(f'print({OK!r})'), info=info), [])
        self.assertFalse(info['capped'])
    def test_default_limit_is_three_gib_and_leaves_room_over_the_measured_peak(self):
        self.assertEqual(runner.WORKER_MEMORY, 3 * 1024 ** 3)

    def alive(self, pid):
        import ctypes
        k = ctypes.windll.kernel32;k.OpenProcess.restype = ctypes.c_void_p;h = k.OpenProcess(0x00100000, False, pid)        # SYNCHRONIZE
        if not h: return False
        try: return k.WaitForSingleObject(ctypes.c_void_p(h), 0) == 0x102                                                    # WAIT_TIMEOUT: still running
        finally: k.CloseHandle(ctypes.c_void_p(h))
    def test_closing_the_job_ends_everything_it_started(self):
        spawn = "import subprocess,sys,time;c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);print(c.pid,flush=True);time.sleep(60)"
        job = winjob.MemoryJob.create(1 << 30);parent = subprocess.Popen([sys.executable, '-c', spawn], stdout=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertTrue(job.add(parent));grandchild = int(parent.stdout.readline());self.assertTrue(self.alive(grandchild));self.assertTrue(self.alive(parent.pid))
            job.close()
            self.assertEqual(parent.wait(timeout=10) is not None, True);import time;end = time.monotonic() + 5
            while self.alive(grandchild) and time.monotonic() < end: time.sleep(.05)
            self.assertFalse(self.alive(grandchild))
        finally:
            job.close();parent.stdout.close()
            if parent.poll() is None: parent.kill()
    def test_cancel_still_stops_the_whole_tree(self):
        import threading, time
        spawn = "import subprocess,sys,time;sys.stdin.read();c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);print(c.pid,flush=True);time.sleep(60)"
        cancel = threading.Event();threading.Timer(1.0, cancel.set).start();start = time.monotonic()
        with self.assertRaises(runner.Cancelled): runner.run_job({}, cancel=cancel, command=[sys.executable, '-c', spawn])
        self.assertLess(time.monotonic() - start, 10)

class RealWorker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name).resolve();self.src = self.root / 'wide.png';Image.new('RGB', (5000, 4000), (200, 120, 40)).save(self.src)    # 20 MP, tiny file
    def tearDown(self): self.tmp.cleanup()
    def job(self, target='JPEG'): return {'paths': [str(self.src)], 'target': target, 'output': str(self.root)}
    @unittest.skipUnless(WIN, 'Windows job objects')
    def test_a_real_conversion_over_the_limit_reports_the_memory_message(self):
        with self.assertRaisesRegex(ValueError, 'more memory than a conversion is allowed'): runner.run_job(self.job(), memory_limit=180 * MiB)
        self.assertEqual([p.name for p in self.root.iterdir()], ['wide.png'])               # nothing half-written is left behind
    def test_a_real_conversion_under_the_default_limit_works(self):
        info = {};out = runner.run_job(self.job(), info=info);self.assertTrue(Path(out[0]).is_file())
        if WIN: self.assertTrue(info['capped']);self.assertLess(info['peak_memory'], runner.WORKER_MEMORY // 3)
    def test_tools_and_ffmpeg_style_children_share_the_limit(self):
        if not WIN: self.skipTest('Windows job objects')
        info = {};runner.run_job({'target': 'tool:edit_image', 'paths': [str(self.src)], 'output': str(self.root), 'params': {'exposure': .5, 'vignette': .4}}, info=info);self.assertGreater(info['peak_memory'], 100 * MiB)

FFMPEG = os.environ.get('OT_FFMPEG') or os.environ.get('OT_TEST_FFMPEG')

@unittest.skipUnless(WIN and FFMPEG, 'Windows job objects and FFmpeg (set OT_FFMPEG)')
class FfmpegChild(unittest.TestCase):
    """FFmpeg is started by the worker, so it must count against the same limit."""
    def test_ffmpeg_shares_the_limit_of_its_worker(self):
        with tempfile.TemporaryDirectory() as d:
            clip = Path(d) / 'v.mp4';subprocess.run([FFMPEG, '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=size=1920x1080:rate=30', '-t', '1', '-pix_fmt', 'yuv420p', str(clip)], check=True)
            job = {'paths': [str(clip)], 'target': 'tool:compress', 'output': d, 'params': {'level': 'strong'}, 'ffmpeg': FFMPEG};info = {}
            self.assertTrue(Path(runner.run_job(job, info=info)[0]).is_file());self.assertGreater(info['peak_memory'], 250 * MiB)        # far more than the Python worker alone
            with self.assertRaisesRegex(ValueError, 'more memory than a conversion is allowed'): runner.run_job(job, memory_limit=120 * MiB)

@unittest.skipUnless(WIN and os.environ.get('OT_SLOW'), 'slow: set OT_SLOW=1 on Windows (40-megapixel encodes)')
class WorstCase(unittest.TestCase):
    """The heaviest legitimate jobs must fit with room to spare, or the cap would break real work."""
    def test_forty_megapixel_avif_and_heic_fit_under_the_default_cap(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'big.png';Image.effect_noise((7000, 5700), 60).convert('RGB').save(src)
            for target in ('AVIF', 'HEIC'):
                info = {};runner.run_job({'paths': [str(src)], 'target': target, 'output': d}, info=info);print(target, 'peak MiB', info['peak_memory'] // MiB)
                self.assertLess(info['peak_memory'], runner.WORKER_MEMORY * .6, target)

if __name__ == '__main__': unittest.main()
