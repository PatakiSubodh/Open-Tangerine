# Open Tangerine — Windows and Linux trial 0.2.0

This is an early cross-platform desktop edition, not a port of every Mac feature.
No account, telemetry, uploads, administrator service or automatic downloads.

## Install

- **Windows 10/11 x64:** extract the entire Windows ZIP into a local folder. Run `OpenTangerine.exe` inside it. Keep `_internal` alongside it. This trial is unsigned; Windows may warn about an unknown publisher. Do not disable Defender or SmartScreen globally. Do not run a file flagged as malware; report the exact warning.
- **Linux x64:** Ubuntu 24.04 or a compatible glibc 2.39+ desktop. Extract the `.tar.gz`, then run `OpenTangerine`. X11 or Wayland desktop libraries are required. Other distributions and ARM are unverified. No root installation is needed.
- Keep this folder to uninstall/remove it later. Updating: quit the app, extract the new package into a separate folder and launch it. Keep the old folder if you want rollback.
- Check the asset's SHA-256 against its companion `.sha256` file. This detects corruption; it is not a publisher signature.

## Use

Drop local files **into the app window**, or click Add files. Choose an output/tool and Convert files. Multiple files are processed sequentially; a failure does not stop later files. Outputs go beside originals, or into your selected folder. Existing files are never replaced. Completed outputs remain if a batch is cancelled. Per-file rows show failures.

Images: PNG, JPEG, WebP, TIFF and BMP output; PNG/JPEG/WebP/TIFF/BMP/AVIF input. JPEG transparency is flattened against white. Optional maximum-side resizing and clockwise rotation. Animated and multipage images are rejected instead of silently discarding frames. HEIC, SVG and RAW are not supported by this trial.

PDF: image to PDF, merge, split into single-page files, extract existing text. No OCR, Word conversion, encrypted PDFs or general Office support. PDF operations can retain active content/links; this is not a PDF sanitizer.

Media: MP4, WebM, MP3, WAV, FLAC and Ogg output from supported local audio/video inputs. Select a **trusted, separately installed FFmpeg executable** using Set FFmpeg. The app does not install or bundle it. Codec support depends on that installation. No playlists or network URLs. Basic SRT/VTT subtitle conversion and SHA-256 file checksums are also included.

The system-wide Shift drag wheel, physical Mac notch, Mac tool editors, tray mode and per-app exclusions are **not** implemented in this edition. There is no global keyboard interception. The progress panel is inside the app window.

## Limits and safety

100 files per batch, 100 MiB per input, 40 megapixels per image, 200 pages per PDF/merged result, 512 MiB output ceiling. Each conversion uses a separate process with a 180-second parent deadline. FFmpeg jobs have a 150-second deadline and one conversion thread. Linux workers additionally have address-space, CPU and output-file limits. Windows workers do not yet have a hard memory cap. Workers are **not an OS security sandbox**: process trusted files only. No claim of malicious-file immunity or zero errors is made.

Regular-file checks reject direct symlinks/reparse points and devices. Publication uses exclusive atomic links on the same local filesystem (NTFS/ext4 recommended). Cloud/network/removable filesystems may not support this and will return an error. Cancellation or a crash can leave a hidden `.opentangerine-*` working folder in the output directory; remove it only after the app is closed. Successful files from partial PDF splitting or a cancelled batch are retained.

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
