# Open Tangerine — Windows and Linux trial 0.2.2

This is an early cross-platform desktop edition, not a port of every Mac feature.
No account, telemetry, uploads, administrator service or automatic downloads.

## Install

- **Windows 10/11 x64:** extract the entire Windows ZIP into a local folder. Run `OpenTangerine.exe` inside it. Keep `_internal` alongside it. This trial is unsigned; Windows may warn about an unknown publisher. Do not disable Defender or SmartScreen globally. Do not run a file flagged as malware; report the exact warning.
- **Linux x64:** Ubuntu 24.04 or a compatible glibc 2.39+ desktop. Extract the `.tar.gz`, then run `OpenTangerine`. X11 or Wayland desktop libraries are required. Other distributions and ARM are unverified. No root installation is needed.
- Keep this folder to uninstall/remove it later. Updating: quit the app, extract the new package into a separate folder and launch it. Keep the old folder if you want rollback.
- Check the asset's SHA-256 against its companion `.sha256` file. This detects corruption; it is not a publisher signature.

## Use

Drop local files **into the app window**, or click Add files. Choose an output on the glass wheel beside the list (contributed by @VandanPatell in #2; its panes follow the files you add) or in the Convert to list, then Convert. Multiple files are processed sequentially; a failure does not stop later files. Outputs go where **Settings** says (beside the originals by default), or into a folder you pick for that run. Existing files are never replaced. Completed outputs remain if a batch is cancelled. Per-file rows show failures.

**Settings** (footer of the main window) has three pages. *General*: where converted files go (next to the original, Downloads, Desktop or a folder you choose), whether to show the results in Explorer when a conversion finishes (off by default) and the **theme**. *Formats*: FFmpeg, Tesseract and LibreOffice, each showing Ready with its version, Cannot run with the reason, or Not found with the install command; you can also choose the program yourself. *About*: version, updates, privacy and source links.

The glass wheel has two themes, chosen in **Settings → General → Appearance → Theme** and saved until you change them: **Light** (default), frosted glass, and **Dark**, the main window's charcoal and Tangerine orange.

The experimental Explorer Shift wheel and tray mode of 0.2.2 are not in this build; a new drag wheel replaces them.

Images: PNG, JPEG, WebP, AVIF, TIFF, BMP and HEIC output; PNG/JPEG/WebP/TIFF/BMP/AVIF/HEIC/SVG input. JPEG transparency is flattened against white. Optional maximum-side resizing and clockwise rotation. Animated and multipage images are rejected instead of silently discarding frames; for HEIC only the primary image is converted. SVG is rasterized by Qt at its own size (or scaled to the maximum side), keeping transparency for PNG/WebP/TIFF/HEIC; SVG files must be under 5 MiB. RAW is not supported.

PDF: image to PDF, merge, split into single-page files, extract existing text, render pages to PNG/JPEG (up to 300 dpi, within the pixel limit), and PDF to DOCX (page text, or a page image for scanned pages; layout is not reproduced). Every PDF and DOCX Open Tangerine creates (image to PDF, text to PDF, image to DOCX, PDF to DOCX) uses A4 pages. Text (`.txt`, `.md`, `.log`, up to 5 MiB) converts to PDF (Latin text keeps real, selectable text; other scripts become an image PDF and need a system font), to PNG/JPEG (one tall image, limited by the pixel cap) and to SRT/VTT (timings are invented at about 0.35 s per word, as on the Mac). SRT/VTT convert to plain text. No encrypted PDFs. PDF operations can retain active content/links; this is not a PDF sanitizer.

**OCR → Text** reads images and scanned PDFs (up to 50 pages, rendered at 300 dpi) into a `.txt` file; **OCR → Searchable PDF** keeps the pages and adds a selectable text layer. Small images are enlarged, contrast is stretched, dark-mode screenshots are inverted and sparse layouts are retried automatically. It needs a **separately installed Tesseract** (found automatically on PATH and in the usual install folders, or chosen in **Settings**), plus the language data you need. Enter a language code such as `eng` or `eng+deu` in the OCR language box. Not bundled or downloaded.

**Office → PDF** converts Word, Excel, PowerPoint and OpenDocument files (doc, docx, odt, rtf, xls, xlsx, ods, ppt, pptx, odp). It needs a **trusted, separately installed LibreOffice**; it is found automatically, or point **Settings** at `soffice.exe` / `soffice`. Each conversion runs headless on a private copy with a throw-away profile, and the result must be a valid PDF of at most 200 pages. Layout can differ from Microsoft Office.

Media: MP4, WebM, MOV, MKV, AVI, WMV, animated GIF (at most 15 s, 480 px wide, 12 fps), MP3, M4A, WAV, FLAC, Ogg, Opus, AIFF and WMA output from supported local audio/video inputs. Needs a **separately installed FFmpeg** (found automatically, or chosen in **Settings**). The app does not install or bundle it. Codec support depends on that installation (for example libopus, wmav2 and libx264). GIF input converts to MP4, WebM, MOV, MKV, AVI or WMV; animated GIF to images is rejected. No playlists or network URLs. Basic SRT/VTT subtitle conversion and SHA-256 file checksums are also included.

## Limits and safety

100 files per batch, 100 MiB per input, 40 megapixels per image, 200 pages per PDF/merged result, 512 MiB output ceiling. Each conversion uses a separate process with a 180-second parent deadline (16 minutes for OCR). FFmpeg jobs have a 150-second deadline and bounded decoder, encoder and filter threads. Linux workers additionally have address-space, CPU and output-file limits. Each Windows worker runs in a job object limited to 3 GiB of memory in total, counting FFmpeg, Tesseract or LibreOffice if it starts them; a file that needs more fails with a clear message, and the job's processes are ended if the app exits. If Windows refuses to create the job the conversion still runs without the cap. Workers are **not an OS security sandbox**: process trusted files only. No claim of malicious-file immunity or zero errors is made.

Regular-file checks reject direct symlinks/reparse points and devices. Publication prefers atomic links and falls back to exclusive creation/copy on FAT32/exFAT. Existing destinations are never replaced. The fallback is not atomic: a hard crash can leave a partial output. Parent-owned staging is cleaned after ordinary cancellation/timeouts; an app or machine crash can still leave a hidden `.opentangerine-*` working folder. Remove leftovers only after the app is closed. Successful files from partial PDF splitting or a cancelled batch are retained.

## Build and test

Python 3.12 recommended. In a virtual environment:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
python -m pip install pyinstaller==6.22.3
python package.py
```

Build separately on Windows and Linux. The CI tests conversion, corruption, limits, naming collisions, original-file preservation, cancellation, timeouts and Qt window startup before packaging. Packaged executables receive a startup and real conversion smoke test. Automated CI does not establish compatibility with every desktop, GPU, codec or antivirus product.

Source: https://github.com/sintaxerrorpvtltd/Open-Tangerine/tree/main/Desktop
Downloads: https://sintaxerrorpvtltd.github.io/Open-Tangerine/#desktop
Copyright 2026 Sintax Error Private Limited. GPL-3.0-only; dependencies retain their licenses. Qt libraries are distributed dynamically in `_internal` and can be replaced with compatible builds. Dependency versions and license texts are included. For corresponding dependency source, use the exact version tags at https://code.qt.io/pyside/pyside-setup.git/ , https://code.qt.io/qt/qtbase.git/ , https://github.com/python-pillow/Pillow and https://github.com/py-pdf/pypdf . No modifications are made to those dependencies. Python is included under the PSF license; PyInstaller's bootloader uses its distribution exception.

Linux GUI packaging is exercised with the real xcb plugin under Xvfb; this does not verify every physical desktop or Wayland compositor.
