import types
import unittest
from unittest.mock import patch
import numpy as np

from voice_changer.engine import VoiceEngine


class EngineTests(unittest.TestCase):
    def run_engine(self, fail=False):
        events, outputs, state = [], [], {}
        class API:
            def prepare(self, model, pitch, frames):
                state['prepared'] = (model, pitch, frames)
            def convert(self, chunk):
                if fail:
                    raise RuntimeError('GPU unavailable')
                return chunk / 2
        class Stream:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
            def __enter__(self):
                if 'blocksize' in self.kwargs:
                    # Simulate an overloaded capture thread before inference.
                    for value in (.2, .4, .6):
                        self.kwargs['callback'](np.full((6144, 1), value, np.float32), 6144, None, None)
                else:
                    state['output'] = self.kwargs['callback']
                return self
            def __exit__(self, *args):
                state['closed'] = state.get('closed', 0) + 1
        sd = types.SimpleNamespace(InputStream=Stream, OutputStream=Stream,
                  check_input_settings=lambda **kw: None, check_output_settings=lambda **kw: None)
        def notify(kind, value):
            events.append((kind, value))
            if kind == 'metrics':
                block = np.empty((6144, 2), dtype=np.float32)
                state['output'](block, 6144, None, None)
                outputs.append(block)
                engine.stop()
        engine = VoiceEngine(API(), notify)
        with patch.dict('sys.modules', {'sounddevice': sd}):
            engine._run(1, 2, 2, .128, 'female', 6)
        # Callback after stop must emit silence, never dry input.
        after_stop = np.ones((64, 2), np.float32)
        state['output'](after_stop, 64, None, None)
        np.testing.assert_array_equal(after_stop, np.zeros((64, 2)))
        self.assertEqual(state['closed'], 2)
        self.assertEqual(events[-1][0], 'stopped')
        self.assertEqual(state['prepared'], ('female', 6, 6144))
        return events, outputs

    def test_streaming_uses_latest_audio_and_outputs_converted_stereo(self):
        events, outputs = self.run_engine()
        np.testing.assert_allclose(outputs[0], .3, atol=1e-6)
        metric = next(value for kind, value in events if kind == 'metrics')
        self.assertEqual(metric['dropped'], 2)

    def test_inference_failure_closes_streams_and_mutes(self):
        events, outputs = self.run_engine(fail=True)
        self.assertEqual(outputs, [])
        self.assertIn(('error', 'GPU unavailable'), events)
