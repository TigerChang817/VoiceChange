# Build on Windows: python -m PyInstaller --noconfirm VoiceChange.spec
from PyInstaller.utils.hooks import collect_dynamic_libs
import sys

a = Analysis(['desktop.py'], pathex=[],
             binaries=collect_dynamic_libs('_sounddevice_data') if sys.platform == 'win32' else [],
             datas=[],
             hiddenimports=['_sounddevice_data', 'voice_changer.launcher'],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VoiceChange',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='VoiceChange')
