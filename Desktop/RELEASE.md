# Windows/Linux desktop 0.2.2 — glass wheel and safer background use

Thanks to @VandanPatell for the glass wheel/tray contribution in #2, and @eklavyamathur9 for the earlier reliability report in #3.

- Glass format picker in the app window on Windows and Linux.
- Opt-in experimental Windows Explorer/Desktop Shift drag wheel. Start a file drag and hold Shift briefly; Escape cancels. Other editors and Shift typing do not trigger it. Windows PowerShell reads selections locally; lookup can take a moment.
- Validate actual dropped files and require Copy semantics, including Move-only rejection. Originals remain unchanged.
- Windows tray mode is optional. Start with a visible window; Run in background hides it to the tray. No tray means no hidden default app. Quit cancels and waits for active work.
- Preserve all 0.2.1 fixes: bounded FFmpeg threads, FAT/exFAT fallback, merge row results, checksum safety, cancellation cleanup and bundled notices/source.
- Website badge moved to the hero; clearer explanation of the separate Mac trial’s Apple verification warning.

No new conversion dependencies. Office converters from #2 are deferred for separate review under #11. No Linux global wheel or physical notch. This is an unsigned early trial; Windows has no hard memory cap and workers are not an OS sandbox. Live Windows Explorer interactions across desktop configurations remain experimental; automated native-platform conversion, Qt drop and packaged-startup checks are required before publication. Keep the previous package for rollback. Mac binary remains 0.1.10 and is not Apple-notarized.
