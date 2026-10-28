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

PDF: image to PDF, merge, split into single-page files, extract existing text, render pages to PNG/JPEG (up to 300 dpi, within the pixel limit), and PDF to DOCX (page text, or a page image for scanned pages; layout is not reproduced). Every PDF and DOCX Open Tangerine creates (image to PDF, text to PDF, image to DOCX, PDF to DOCX) uses A4 pages; Create a PDF also offers US Letter or the size of each image. Text (`.txt`, `.md`, `.log`, up to 5 MiB) converts to PDF (Latin text keeps real, selectable text; other scripts become an image PDF and need a system font), to PNG/JPEG (one tall image, limited by the pixel cap) and to SRT/VTT (timings are invented at about 0.35 s per word, as on the Mac). SRT/VTT convert to plain text. No encrypted PDFs. PDF operations can retain active content/links; this is not a PDF sanitizer.

**OCR → Text** reads images and scanned PDFs (up to 50 pages, rendered at 300 dpi) into a `.txt` file; **OCR → Searchable PDF** keeps the pages and adds a selectable text layer. Small images are enlarged, contrast is stretched, dark-mode screenshots are inverted and sparse layouts are retried automatically. It needs a **separately installed Tesseract** (found automatically on PATH and in the usual install folders, or chosen in **Settings**), plus the language data you need. Enter a language code such as `eng` or `eng+deu` in the OCR language box. Not bundled or downloaded.

**Office → PDF** converts Word, Excel, PowerPoint and OpenDocument files (doc, docx, odt, rtf, xls, xlsx, ods, ppt, pptx, odp). It needs a **trusted, separately installed LibreOffice**; it is found automatically, or point **Settings** at `soffice.exe` / `soffice`. Each conversion runs headless on a private copy with a throw-away profile, and the result must be a valid PDF of at most 200 pages. Layout can differ from Microsoft Office.

Media: MP4, WebM, MOV, MKV, AVI, WMV, animated GIF (at most 15 s, 480 px wide, 12 fps), MP3, M4A, WAV, FLAC, Ogg, Opus, AIFF and WMA output from supported local audio/video inputs. Needs a **separately installed FFmpeg** (found automatically, or chosen in **Settings**). The app does not install or bundle it. Codec support depends on that installation (for example libopus, wmav2 and libx264). GIF input converts to MP4, WebM, MOV, MKV, AVI or WMV; animated GIF to images is rejected. No playlists or network URLs. Basic SRT/VTT subtitle conversion and SHA-256 file checksums are also included.

## Tools

Each tool opens its own window with the options on the right and, where it helps, a live preview or editing canvas on the left. Results are new files in the Settings output folder (beside the original by default); nothing is overwritten, and a failed run leaves no partial file. Tools run through the same isolated worker as conversions, with the same limits (100 MiB per input, 40 megapixels, 200 PDF pages, 512 MiB output) and a 30-minute ceiling for long video jobs.

| Files | Tools |
|---|---|
| **Images** | Edit photo (17 controls in four groups: exposure, brightness, contrast, highlights, shadows · colour, vibrance, temperature, tint, sepia, black and white · sharpness, clarity, dehaze, noise reduction · grain, vignette; live preview and Reset all) · Crop (drag a box, optional fixed shape) · Redact (draw boxes; black, blur or pixelate) · Resize (percent, width, height or fit; many files at once) · Rotate and flip · Add a background (padding, shape, colour or blurred photo) · Create a PDF from several images (A4 by default, or Letter, or the size of each image; in your order) · Create a collage |
| **PDF** | Merge (in your order) · Organize pages (thumbnails; reorder, rotate, remove) · Split (every page, or ranges such as `1-3, 5, 8-`) |
| **Any image, PDF, audio or video** | Compress · Edit metadata (remove everything, or location only for photos; set title and author for PDF, audio and video) |
| **Video** *(FFmpeg)* | Trim · Normalize volume · Change speed · Crop to a shape · Join videos · Split into parts or at times · Save frames · **Redact** (draw boxes on a frame; each hidden for its own time range; black, blur or pixelate; sound is kept) |
| **Audio** *(FFmpeg)* | Trim (the same Trim tool as video) · Normalize volume · Mono/stereo/left/right/swap · Waveform visualizer video · **Bleep** (cover time ranges with a tone or silence) |

Notes: video and audio tools need FFmpeg (found automatically, or chosen in **Settings**; the tool window offers the button if it is missing); video results are MP4 (H.264/AAC) and audio keeps its own format. Compress turns audio into MP3, refuses to produce a file that is not smaller, and PDF compression is lossless clean-up only (it does not downsample images). Blur and pixelate redaction can sometimes be reversed; use the black box for sensitive data. The previews in tool windows are decoded inside the app process, not the isolated worker, so open only files you trust. Redacting video re-encodes the picture and leaves the sound track alone; bleeping re-encodes the audio in its own format. Photo adjustments approximate the Mac's Core Image filters and are not pixel-identical; film grain differs slightly between the preview and the saved result.

## Limits and safety

100 files per batch, 100 MiB per input, 40 megapixels per image, 200 pages per PDF/merged result, 512 MiB output ceiling. Each conversion uses a separate process with a 180-second parent deadline (16 minutes for OCR, 30 minutes for editing tools). FFmpeg conversions have a 150-second deadline and bounded decoder, encoder and filter threads. Linux workers additionally have address-space, CPU and output-file limits. Each Windows worker runs in a job object limited to 3 GiB of memory in total, counting FFmpeg, Tesseract or LibreOffice if it starts them; a file that needs more fails with a clear message, and the job's processes are ended if the app exits. If Windows refuses to create the job the conversion still runs without the cap. Workers are **not an OS security sandbox**: process trusted files only. No claim of malicious-file immunity or zero errors is made.

Regular-file checks reject direct symlinks/reparse points and devices. Publication prefers atomic links and falls back to exclusive creation/copy on FAT32/exFAT. Existing destinations are never replaced. The fallback is not atomic: a hard crash can leave a partial output. Parent-owned staging is cleaned after ordinary cancellation/timeouts; an app or machine crash can still leave a hidden `.opentangerine-*` working folder. Remove leftovers only after the app is closed. Successful files from partial PDF splitting or a cancelled batch are retained.

## Build and test

Python 3.12 recommended. In a virtual environment:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v   # set OT_FFMPEG to an ffmpeg executable to also run the media and redaction tests
python app.py
python -m pip install pyinstaller==6.22.3
python package.py
```

Build separately on Windows and Linux. The CI tests conversion, corruption, limits, naming collisions, original-file preservation, cancellation, timeouts and Qt window startup before packaging. Packaged executables receive a startup and real conversion smoke test. Automated CI does not establish compatibility with every desktop, GPU, codec or antivirus product.

Source: https://github.com/sintaxerrorpvtltd/Open-Tangerine/tree/main/Desktop
Downloads: https://sintaxerrorpvtltd.github.io/Open-Tangerine/#desktop
Copyright 2026 Sintax Error Private Limited. GPL-3.0-only; dependencies retain their licenses. Qt libraries are distributed dynamically in `_internal` and can be replaced with compatible builds. Dependency versions and license texts are included. For corresponding dependency source, use the exact version tags at https://code.qt.io/pyside/pyside-setup.git/ , https://code.qt.io/qt/qtbase.git/ , https://github.com/python-pillow/Pillow and https://github.com/py-pdf/pypdf . No modifications are made to those dependencies. Python is included under the PSF license; PyInstaller's bootloader uses its distribution exception.

Linux GUI packaging is exercised with the real xcb plugin under Xvfb; this does not verify every physical desktop or Wayland compositor.
