Windows and Linux desktop trial 0.3.0. **Still a smaller feature set than the Mac app; see Desktop/README.md for the exact capabilities and limits.**

- Windows 10/11 x64 portable ZIP; Linux x64 Ubuntu 24.04 / glibc 2.39+ tar.gz.
- Windows: Shift / Alt / Ctrl+Shift drag wheel (convert, tools, file actions), system tray, start with Windows, per-application exclusions and a Settings window (output folder, helper programs, About).
- Windows and Linux: the glass format wheel from @VandanPatell's #2 is back beside the file list, and its panes now follow the files you add.
- Light (frosted glass) and Dark (charcoal and Tangerine) themes for the wheels and, on Windows, the progress card. The progress card shows full messages without cutting them off, stays for at least their reading time, pauses on hover and can sit in any of five screen positions.
- Images: PNG, JPEG, WebP, AVIF, TIFF, BMP, HEIC. Edit photo with 17 controls and live preview, crop, redact, resize, rotate, background, collage.
- Documents: image to PDF or DOCX, PDF merge/split/text, PDF pages to PNG/JPEG, PDF to DOCX, text to PDF/PNG/JPEG/SRT/VTT. New PDFs and DOCX files are A4.
- Separate files or one file: several files, even a mix of images, text, PDFs and Office documents, can become one PDF or Word file in list order. Every page of a combined PDF, and Office → PDF output, is A4 (landscape A4 for wide pages). Choose *One file* in the window, or release on the outer half of a PDF/DOCX tile on the drag wheel.
- Audio and video with your own trusted FFmpeg: MP4, WebM, MOV, MKV, AVI, WMV, GIF, MP3, M4A, WAV, FLAC, Ogg, Opus, AIFF, WMA; redact video areas and bleep audio.
- Originals retained; exclusive output naming; separate workers, cancellation, time and output limits. Windows workers also run under a 3 GiB memory cap (a Windows job object); Linux workers have an address-space limit. These are not operating-system sandboxes; process trusted files.
- Source, dependency versions and license texts are included in each package.

Both platform CI jobs must pass conversion/safety tests and packaged startup/conversion smoke checks before this release is published. This is not a guarantee of compatibility with every machine. Unsigned Windows binary; no administrator access required. No physical-notch integration or archive tools.

Extract the full archive, then run OpenTangerine.exe (Windows) or OpenTangerine (Linux). Keep the _internal folder alongside the executable. Compare SHA-256 with the companion checksum. Do not disable OS protection globally.

Full installation, capabilities and limitations: https://github.com/sintaxerrorpvtltd/Open-Tangerine/blob/main/Desktop/README.md
Mac users: keep using the separate macOS release.
