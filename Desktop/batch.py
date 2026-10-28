"""Sequential batch runner for the main window."""
import threading
from PySide6.QtCore import QThread, Signal
from runner import run_job, Cancelled

class Batch(QThread):
    result=Signal(int,str,list)
    progress=Signal(int,int)
    def __init__(self,paths,target,options):
        super().__init__();self.paths=paths;self.target=target;self.options=options;self.cancel=threading.Event()
    def combined(self):
        """One job for the whole list (Merge PDFs, and tools that join files) instead of one per file."""
        if self.target.startswith('tool:'):
            import toolops
            return toolops.TOOLS[self.target[5:]].combined
        return self.target=='Merge PDFs'
    def run(self):
        groups=[self.paths] if self.combined() else [[p] for p in self.paths]
        for i,paths in enumerate(groups):
            if self.cancel.is_set(): break
            try:
                outputs=run_job(dict(paths=paths,target=self.target,**self.options),self.cancel)
                self.result.emit(i,'Done',outputs)
            except Cancelled as e:
                self.result.emit(i,str(e),[]);break
            except Exception as e:self.result.emit(i,str(e),[])
            self.progress.emit(i+1,len(groups))
