"""Windows desktop entry point used by PyInstaller."""
import os

from voice_changer.app import main

if __name__ == '__main__':
    if os.environ.get('VOICECHANGE_SMOKE_TEST') == '1':
        import tkinter as tk
        import sounddevice  # Validate that the packaged PortAudio DLL loads.
        from voice_changer.app import App
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        app = App(root)
        root.after(2000, app.close)
        root.mainloop()
        if errors:
            raise RuntimeError(f'GUI callback failed: {errors}')
    else:
        main()
