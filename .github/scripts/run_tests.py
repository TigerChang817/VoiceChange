"""Expose failure diagnostics as Actions annotations, retaining test exit status."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
suite = unittest.defaultTestLoader.discover('tests')
result = unittest.TextTestRunner(verbosity=2).run(suite)
for test, trace in result.failures + result.errors:
    message = f'{test}\n{trace}'.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print(f'::error title=Windows test failure::{message}', flush=True)
sys.exit(0 if result.wasSuccessful() else 1)
