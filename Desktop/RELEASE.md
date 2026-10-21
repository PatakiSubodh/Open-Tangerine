# Windows/Linux desktop 0.2.1 — reliability update

Thanks to @eklavyamathur9 for the detailed report in #3.

- Limit FFmpeg decoder and filter threads as well as encoder threads, without raising the Linux memory ceiling.
- Support FAT32/exFAT output through exclusive creation; never overwrite an existing file. A hard crash can leave a partial fallback copy.
- Explicitly include LGPL and Python licence texts, dependency notices and rebuildable source.
- Detect path replacement during canonicalization, improve symlink errors, tolerate recoverable PDF xref problems, normalize short SRT timestamps and reject ambiguous checksum filenames.
- Show PDF merge results on every input row; force Copy drag/drop semantics; improve worker cleanup and signal errors.
- Add Linux xcb/Xvfb packaged startup, archived-package validation and checksum verification before publishing.

This remains an unsigned early trial with a window-based interface. Global Windows Shift wheels are being reviewed separately; they are not in this release. Windows has no hard memory cap. Workers are not an OS sandbox. Use trusted files. Keep the previous package for rollback.
