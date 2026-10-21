import errno, json, os, signal, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine, runner
from engine import convert, publish, ConversionError
from PIL import Image
from pypdf import PdfWriter

class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.src=self.root/'input.png';Image.new('RGB',(8,8),'red').save(self.src)
    def tearDown(self):self.tmp.cleanup()
    def job(self,target='JPEG',path=None):return {'paths':[str(path or self.src)],'target':target,'output':str(self.root)}
    def test_exclusive_copy_fallback_collision(self):
        stage=self.root/'stage';stage.write_bytes(b'new');existing=self.root/'out.txt';existing.write_bytes(b'original')
        with patch('engine.os.link',side_effect=OSError(errno.EOPNOTSUPP,'unsupported')):
            out=Path(publish(stage,self.root,'out','txt'))
        self.assertEqual(existing.read_bytes(),b'original');self.assertEqual(out.read_bytes(),b'new');self.assertNotEqual(out,existing)
    def test_copy_failure_removes_only_partial_output(self):
        stage=self.root/'stage';stage.write_bytes(b'new')
        with patch('engine.os.link',side_effect=OSError(errno.EPERM,'unsupported')),patch('engine.shutil.copyfileobj',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):publish(stage,self.root,'out','txt')
        self.assertFalse((self.root/'out.txt').exists());self.assertEqual(stage.read_bytes(),b'new')
    def test_copy_fallback_does_not_follow_destination_symlink(self):
        victim=self.root/'victim';victim.write_bytes(b'original');link=self.root/'out.txt'
        try:link.symlink_to(victim)
        except OSError:self.skipTest('Symlink privilege unavailable')
        with patch('engine.os.link',side_effect=OSError(errno.EPERM,'unsupported')):out=publish(self.src,self.root,'out','txt')
        self.assertNotEqual(out,str(link));self.assertEqual(victim.read_bytes(),b'original')
    def test_changed_identity_rejected(self):
        other=self.root/'other';other.write_bytes(b'other')
        with patch.object(Path,'resolve',return_value=other):
            with self.assertRaisesRegex(ConversionError,'Path changed'):engine.source_file(self.src)
            with self.assertRaisesRegex(ConversionError,'Path changed'):engine.output_folder(self.root)
    def test_pdf_recoverable_xref(self):
        p=self.root/'input.pdf';w=PdfWriter();w.add_blank_page(10,10)
        with p.open('wb') as f:w.write(f)
        data=p.read_bytes();import re
        data=re.sub(rb'startxref\n\d+',b'startxref\n1',data);p.write_bytes(data)
        self.assertTrue(convert(self.job('PDF → Text',p)))
    def test_short_srt(self):
        p=self.root/'short.srt';p.write_text('1\n00:01,200 --> 00:02,300\nHello\n')
        out=Path(convert(self.job('SRT → VTT',p))[0]);self.assertIn('00:00:01.200 --> 00:00:02.300',out.read_text())
    @unittest.skipIf(os.name=='nt','Windows rejects newline filenames')
    def test_checksum_newline_rejected(self):
        p=self.root/'forged\nrecord';p.write_bytes(b'hi')
        with self.assertRaisesRegex(ConversionError,'Rename'):convert(self.job('SHA-256',p))
    def test_worker_staging_cleanup_success_and_failure(self):
        runner.run_job(self.job());self.assertFalse(list(self.root.glob('.opentangerine-*')))
        self.src.write_bytes(b'bad')
        with self.assertRaises(ValueError):runner.run_job(self.job())
        self.assertFalse(list(self.root.glob('.opentangerine-*')))
    def test_cancelled_worker_staging_cleanup(self):
        event=threading.Event();event.set()
        with self.assertRaises(runner.Cancelled):runner.run_job(self.job(),cancel=event)
        self.assertFalse(list(self.root.glob('.opentangerine-*')))
    @unittest.skipIf(os.name=='nt','POSIX signal reporting')
    def test_cpu_signal_message(self):
        with self.assertRaisesRegex(ValueError,'CPU time limit'):
            runner.run_job({},command=[sys.executable,'-c','import os,signal;os.kill(os.getpid(),signal.SIGXCPU)'])
    @unittest.skipUnless(os.name=='nt','Windows taskkill fallback')
    def test_taskkill_failure_still_kills_worker(self):
        for error in [FileNotFoundError(),subprocess.TimeoutExpired('taskkill',10)]:
            proc=Mock();proc.poll.return_value=None
            with patch('runner.subprocess.run',side_effect=error):runner.stop(proc)
            proc.kill.assert_called_once();proc.wait.assert_called_once()
    def test_ffmpeg_decoder_and_filter_limits(self):
        p=self.root/'clip.mp4';p.write_bytes(b'fake');stage=self.root/'out';stage.write_bytes(b'output')
        proc=Mock();proc.poll.return_value=0;proc.returncode=0
        with patch('engine.subprocess.Popen',return_value=proc) as popen:
            engine.media(p,stage,'MP4',str(Path(sys.executable).resolve()))
        cmd=popen.call_args.args[0];before=cmd[:cmd.index('-i')];after=cmd[cmd.index('-i')+2:]
        self.assertEqual(before[before.index('-threads')+1],'1');self.assertEqual(after[after.index('-threads')+1],'1')
        self.assertEqual(before[before.index('-filter_threads')+1],'1')
if __name__=='__main__':unittest.main()
