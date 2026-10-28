Windows and Linux desktop trial 0.3.0. **Still a smaller feature set than the Mac app; see Desktop/README.md for the exact capabilities and limits.**

- Windows 10/11 x64 portable ZIP; Linux x64 Ubuntu 24.04 / glibc 2.39+ tar.gz.
- Windows: opt-in Shift / Alt / Ctrl+Shift drag wheel (convert, tools, file actions; off until you turn it on in Settings or the tray), system tray, start with Windows, per-application exclusions and a Settings window (output folder, helper programs, About).
- Windows and Linux: the glass format wheel from @VandanPatell's #2 is back beside the file list, and its panes now follow the files you add.
- Drag-wheel conversions keep the progress island from #16 by default; Settings → Drag wheel → Conversion progress switches to the progress card (an island turned Off in 0.2.3 becomes the card). File actions use the card.
- Every window fits the screen it is on, at any resolution and display scaling: the main window, Settings and the tool windows open inside the usable area, scroll instead of overlapping when the screen is smaller, and shrink when moved to a smaller monitor.
- Light (frosted glass) and Dark (charcoal and Tangerine) themes for the wheels and, on Windows, the progress card. The progress card shows full messages without cutting them off, stays for at least their reading time, pauses on hover and can sit in any of five screen positions.
- Images: PNG, JPEG, WebP, AVIF, TIFF, BMP, HEIC. Edit photo with 17 controls and live preview, crop, redact, resize, rotate, background, collage.
- Documents: Word .docx to plain text or a text-only PDF (from 0.2.3), image to PDF or DOCX, PDF merge/split/text, PDF pages to PNG/JPEG, PDF to DOCX, text to PDF/PNG/JPEG/SRT/VTT. New PDFs and DOCX files are A4.
- Separate files or one file: several files, even a mix of images, text, PDFs and Office documents, can become one PDF or Word file in list order. Every page of a combined PDF, and Office → PDF output, is A4 (landscape A4 for wide pages). Choose *One file* in the window, or release on the outer half of a PDF/DOCX tile on the drag wheel.
- OCR to text or a searchable PDF with your own Tesseract, and Office documents to PDF with your own LibreOffice. Neither is bundled or downloaded.
- Audio and video with your own trusted FFmpeg: MP4, WebM, MOV, MKV, AVI, WMV, GIF, MP3, M4A, WAV, FLAC, Ogg, Opus, AIFF, WMA; redact video areas and bleep audio.
- Originals retained; exclusive output naming; separate workers, cancellation, time and output limits. Windows workers also run under a 3 GiB memory cap (a Windows job object); Linux workers have an address-space limit. These are not operating-system sandboxes; process trusted files.
- Source, dependency versions and license texts are included in each package.

Both platform CI jobs must pass conversion/safety tests and packaged startup/conversion smoke checks before this release is published. This is not a guarantee of compatibility with every machine. Unsigned Windows binary; no administrator access required. No physical-notch integration or archive tools.

Extract the full archive, then run OpenTangerine.exe (Windows) or OpenTangerine (Linux). Keep the _internal folder alongside the executable. Compare SHA-256 with the companion checksum. Do not disable OS protection globally.

Full installation, capabilities and limitations: https://github.com/sintaxerrorpvtltd/Open-Tangerine/blob/main/Desktop/README.md
Mac users: keep using the separate macOS release.
