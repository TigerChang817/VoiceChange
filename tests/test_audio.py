import base64
import io
import json
import unittest
from unittest.mock import patch
from urllib import error

import numpy as np
from voice_changer.audio import LocalRVC, encode_pcm, decode_pcm
from voice_changer.engine import PlaybackBuffer


class Response(io.BytesIO):
    pass


class ProtocolTests(unittest.TestCase):
    def test_pcm_is_little_endian_saturates_and_roundtrips(self):
        raw = encode_pcm([-2, -.5, 0, .5, 2])
        self.assertEqual(raw[:2], b'\x01\x80')
        result = decode_pcm(base64.b64encode(raw), 5)
        np.testing.assert_allclose(result, [-.98, -.5, 0, .5, .98], atol=1e-4)
        with self.assertRaises(ValueError):
            encode_pcm([np.nan])

    def test_warmup_silence_and_invalid_payloads(self):
        np.testing.assert_array_equal(decode_pcm('AAA=', 6144), np.zeros(6144))
        for raw in (b'', b'1', b'123456'):
            with self.assertRaises(ValueError):
                decode_pcm(base64.b64encode(raw), 6144)

    def test_actual_pcm_protocol_and_settings_handshake(self):
        api = LocalRVC()
        requests = []
        def open_request(req, timeout):
            from urllib.parse import parse_qs
            path = req.full_url.removeprefix(api.url)
            requests.append((path, req.headers, timeout))
            if path == '/info':
                value = {'modelSlots': [None, {'voiceChangerType': 'RVC', 'modelFile': 'voice.pth', 'name': 'Test', 'slotIndex': 2}, {'voiceChangerType': 'LLVC', 'modelFile': 'other', 'slotIndex': 3}]}
            elif path == '/update_settings':
                fields = parse_qs(req.data.decode())
                key, raw_value = fields['key'][0], fields['val'][0]
                if key == 'passThrough':
                    self.assertEqual(raw_value, 'false')
                    value = {key: False}
                else:
                    value = {key: int(raw_value)}
            elif path == '/test':
                body = json.loads(req.data)
                raw = base64.b64decode(body['buffer'])
                self.assertEqual(len(raw), 6144 * 2)
                self.assertNotEqual(raw[:4], b'RIFF')
                value = {'timestamp': body['timestamp'], 'changedVoiceBase64': body['buffer']}
            else:
                self.fail(path)
            return Response(json.dumps(value).encode())
        with patch.object(api.opener, 'open', side_effect=open_request):
            self.assertEqual(api.models(), ['2: Test'])
            api.prepare('2: Test', 6)
            result = api.convert(np.full(6144, .25, np.float32))
        np.testing.assert_allclose(result, .25, atol=1e-4)
        self.assertEqual(sum(p == '/test' for p, _, _ in requests), 4)
        self.assertEqual(requests[-1][2], 2)
        self.assertTrue(all(api.url.startswith('http://127.0.0.1:') for _ in requests))

    def test_timestamp_mismatch_fails_closed(self):
        api = LocalRVC()
        with patch.object(api, 'call', return_value={'timestamp': -1, 'changedVoiceBase64': 'AAA='}):
            with self.assertRaisesRegex(ValueError, '時間戳'):
                api.convert(np.zeros(6144))

    def test_settings_not_applied_are_rejected(self):
        api = LocalRVC()
        with patch.object(api, 'call', return_value={'passThrough': True}):
            with self.assertRaisesRegex(ValueError, '未套用'):
                api.setting('passThrough', 0)

    def test_connection_failure_has_actionable_error(self):
        api = LocalRVC()
        with patch.object(api.opener, 'open', side_effect=error.URLError('refused')):
            with self.assertRaisesRegex(RuntimeError, '18888'):
                api.models()

    def test_redirects_are_not_followed(self):
        api = LocalRVC()
        handler = next(h for h in api.opener.handlers if hasattr(h, 'redirect_request'))
        self.assertIsNone(handler.redirect_request(None, None, 302, '', {}, 'https://example.org'))


class BufferTests(unittest.TestCase):
    def test_partial_reads_fifo_and_underrun_silence(self):
        buf = PlaybackBuffer(8)
        buf.put([1, 2, 3]); buf.put([4, 5])
        np.testing.assert_array_equal(buf.read(2), [1, 2])
        np.testing.assert_array_equal(buf.read(5), [3, 4, 5, 0, 0])
        self.assertEqual(buf.frames, 0)

    def test_overload_discards_old_audio_and_stays_bounded(self):
        buf = PlaybackBuffer(6)
        buf.put([1, 2, 3, 4]); buf.put([5, 6, 7, 8])
        self.assertEqual(buf.dropped, 4)
        np.testing.assert_array_equal(buf.read(6), [5, 6, 7, 8, 0, 0])
        buf.put(np.arange(20))
        self.assertEqual(buf.frames, 6)
        np.testing.assert_array_equal(buf.read(6), np.arange(14, 20))
