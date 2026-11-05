"""Small PCM blocks over loopback to w-okada's streaming RVC engine."""
import base64
import json
import ssl
import time
from urllib import request, error, parse

import numpy as np

RATE = 48000


def encode_pcm(samples):
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    if not np.isfinite(samples).all():
        raise ValueError('音訊含有無效數值')
    return (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()


def decode_pcm(encoded, frames):
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) % 2 or not raw:
        raise ValueError('引擎回傳無效的 PCM 音訊')
    samples = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768
    # During warmup the upstream engine can return a single silent sample.
    if len(samples) == 1 and samples[0] == 0:
        return np.zeros(frames, dtype=np.float32)
    if len(samples) != frames:
        raise ValueError(f'引擎回傳 {len(samples)} 個取樣，預期 {frames}；請確認引擎版本與 48kHz 設定')
    return np.clip(samples, -.98, .98)


class LocalRVC:
    """w-okada MMVCServerSIO /info, /update_settings, /test protocol."""
    def __init__(self, port=18888, cafile=None):
        scheme = 'https' if cafile else 'http'
        self.url = f'{scheme}://127.0.0.1:{int(port)}'
        self.slots = {}
        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        handlers = [request.ProxyHandler({}), NoRedirect()]
        if cafile:
            handlers.append(request.HTTPSHandler(context=ssl.create_default_context(cafile=str(cafile))))
        self.opener = request.build_opener(*handlers)

    def call(self, path, payload=None, form=False, timeout=30):
        if payload is None:
            body, content_type = None, 'application/json'
        elif form:
            body, content_type = parse.urlencode(payload).encode(), 'application/x-www-form-urlencoded'
        else:
            body, content_type = json.dumps(payload).encode(), 'application/json'
        req = request.Request(self.url + path, data=body, headers={'Content-Type': content_type})
        try:
            with self.opener.open(req, timeout=timeout) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise ValueError('引擎回傳非預期格式，請查看引擎視窗')
            return result
        except error.HTTPError as exc:
            detail = exc.read(1000).decode('utf-8', errors='replace')
            raise RuntimeError(f'AI 引擎錯誤 {exc.code}: {detail}') from exc
        except (error.URLError, TimeoutError) as exc:
            raise RuntimeError(f'無法連接即時引擎或推論逾時（{self.url}）；請檢查引擎狀態。') from exc

    def models(self, timeout=30):
        info = self.call('/info', timeout=timeout)
        slots = info.get('modelSlots')
        if not isinstance(slots, list):
            raise ValueError('不相容的引擎：/info 缺少 modelSlots')
        self.slots = {}
        for slot in slots:
            if slot and slot.get('voiceChangerType') == 'RVC' and slot.get('modelFile'):
                label = f"{slot['slotIndex']}: {slot.get('name') or slot['modelFile']}"
                self.slots[label] = slot['slotIndex']
        return list(self.slots)

    def setting(self, key, value):
        info = self.call('/update_settings', {'key': key, 'val': value}, form=True)
        actual = info.get(key)
        if value in ('true', 'false'):
            value = value == 'true'
        if key not in info or (actual != value and str(actual).lower() != str(value).lower()):
            raise ValueError(f'引擎未套用設定 {key}；請確認使用相容版本')
        return info

    def prepare(self, model, pitch, frames=6144):
        if model not in self.slots:
            raise ValueError('請重新整理並選取已載入的 RVC 模型')
        # Disable both upstream device capture and raw-voice passthrough.
        self.setting('serverAudioStated', 0)
        self.setting('modelSlotIndex', self.slots[model])
        self.setting('passThrough', 'false')
        self.setting('inputSampleRate', RATE)
        self.setting('outputSampleRate', RATE)
        self.setting('recordIO', 0)
        self.setting('gpu', 0)
        self.setting('tran', int(pitch))
        # Warm up GPU/model before opening the microphone. Upstream owns the
        # context buffer, pitch extraction and SOLA overlap; do not repeat here.
        for _ in range(3):
            self.convert(np.zeros(frames, dtype=np.float32), timeout=30)

    def convert(self, samples, timeout=2):
        stamp = time.monotonic_ns()
        result = self.call('/test', {'timestamp': stamp,
             'buffer': base64.b64encode(encode_pcm(samples)).decode()}, timeout=timeout)
        if result.get('timestamp') != stamp:
            raise ValueError('引擎回應時間戳不符')
        return decode_pcm(result['changedVoiceBase64'], len(samples))
