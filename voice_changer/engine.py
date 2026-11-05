"""Audio callbacks only copy data; AI runs on a separate thread."""
from contextlib import ExitStack
from collections import deque
from queue import Queue, Empty, Full
from threading import Event, Lock, Thread
import time

import numpy as np
from .audio import RATE


class PlaybackBuffer:
    def __init__(self, max_frames):
        self.limit = max_frames
        self.chunks = deque()
        self.frames = 0
        self.lock = Lock()
        self.dropped = 0

    def put(self, data):
        data = np.asarray(data, dtype=np.float32).reshape(-1).copy()
        with self.lock:
            if len(data) > self.limit:
                self.dropped += len(data) - self.limit
                data = data[-self.limit:]
            while self.chunks and self.frames + len(data) > self.limit:
                self.dropped += len(self.chunks[0])
                self.frames -= len(self.chunks.popleft())
            self.chunks.append(data)
            self.frames += len(data)

    def read(self, frames):
        out = np.zeros(frames, np.float32)
        with self.lock:
            cursor = 0
            while self.chunks and cursor < frames:
                chunk = self.chunks.popleft()
                count = min(len(chunk), frames - cursor)
                out[cursor:cursor + count] = chunk[:count]
                cursor += count
                self.frames -= count
                if count < len(chunk):
                    self.chunks.appendleft(chunk[count:])
        return out


class OutputMixer:
    """Independent Discord and headphone paths with live volume controls."""
    def __init__(self):
        self.lock = Lock()
        self.enabled = False
        self.output_gain = 1.0
        self.monitor_gain = .5
        self.reset(RATE)

    def reset(self, frames):
        with self.lock:
            self.main = PlaybackBuffer(frames * 2)
            self.monitor = PlaybackBuffer(frames * 2)

    def set_monitor(self, enabled):
        with self.lock:
            self.enabled = bool(enabled)
            self.monitor = PlaybackBuffer(self.main.limit)

    def set_volume(self, output=None, monitor=None):
        with self.lock:
            if output is not None:
                self.output_gain = max(0., min(2., float(output)))
            if monitor is not None:
                self.monitor_gain = max(0., min(1., float(monitor)))

    def put(self, audio):
        with self.lock:
            self.main.put(audio)
            if self.enabled:
                self.monitor.put(audio)

    def read(self, frames, monitor=False):
        with self.lock:
            if monitor and not self.enabled:
                return np.zeros(frames, np.float32)
            buffer = self.monitor if monitor else self.main
            gain = self.monitor_gain if monitor else self.output_gain
            return np.clip(buffer.read(frames) * gain, -.98, .98)


class VoiceEngine:
    def __init__(self, api, notify):
        self.api, self.notify = api, notify
        self.stop_event = Event()
        self.thread = None
        self.mixer = OutputMixer()

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, input_device, output_device, output_channels, seconds, model, pitch, monitor_device=None, monitor_channels=2):
        if self.running:
            raise RuntimeError('上一個音訊工作尚未結束')
        self.stop_event.clear()
        self.thread = Thread(target=self._run, args=(input_device, output_device,
                             output_channels, seconds, model, pitch, monitor_device, monitor_channels), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _run(self, input_device, output_device, channels, seconds, model, pitch, monitor_device=None, monitor_channels=2):
        try:
            import sounddevice as sd
            self.notify('status', '載入模型中，首次啟動可能需要下載基礎模型…')
            frames = round(RATE * seconds)
            self.api.prepare(model, pitch, frames)
            if self.stop_event.is_set():
                return
            incoming = Queue(maxsize=1)
            self.mixer.reset(frames)
            dropped = 0
            last_level = 0.

            def capture(indata, count, timing, status):
                nonlocal dropped, last_level
                last_level = float(np.max(np.abs(indata)))
                if status:
                    self.notify('warning', str(status))
                data = (time.monotonic(), indata[:, 0].copy())
                try:
                    incoming.put_nowait(data)
                except Full:
                    try:
                        incoming.get_nowait()
                        dropped += 1
                    except Empty:
                        pass
                    try:
                        incoming.put_nowait(data)
                    except Full:
                        dropped += 1

            def output(outdata, count, timing, status):
                if self.stop_event.is_set():
                    outdata.fill(0)
                else:
                    outdata[:] = self.mixer.read(count)[:, None]
                if status:
                    self.notify('warning', str(status))

            def monitor_output(outdata, count, timing, status):
                if self.stop_event.is_set():
                    outdata.fill(0)
                else:
                    outdata[:] = self.mixer.read(count, monitor=True)[:, None]
                if status:
                    self.notify('warning', '監聽：' + str(status))

            if monitor_device == output_device:
                raise ValueError('監聽請選耳機，並與 Discord 輸出裝置分開')
            sd.check_input_settings(device=input_device, channels=1, samplerate=RATE)
            sd.check_output_settings(device=output_device, channels=channels, samplerate=RATE)
            with ExitStack() as streams:
                streams.enter_context(sd.OutputStream(device=output_device, channels=channels,
                    samplerate=RATE, dtype='float32', latency='low', callback=output))
                if monitor_device is not None:
                    sd.check_output_settings(device=monitor_device, channels=monitor_channels, samplerate=RATE)
                    streams.enter_context(sd.OutputStream(device=monitor_device, channels=monitor_channels,
                        samplerate=RATE, dtype='float32', latency='low', callback=monitor_output))
                streams.enter_context(sd.InputStream(device=input_device, channels=1, samplerate=RATE,
                    blocksize=frames, dtype='float32', latency='low', callback=capture))
                self.notify('status', '轉換中；請戴耳機，避免回授')
                while not self.stop_event.is_set():
                    try:
                        captured, chunk = incoming.get(timeout=.1)
                    except Empty:
                        continue
                    started = time.monotonic()
                    if started - captured > seconds * 1.5:
                        dropped += 1
                        continue
                    result = self.api.convert(chunk)
                    elapsed = time.monotonic() - started
                    if self.stop_event.is_set():
                        break
                    self.mixer.put(result)
                    self.notify('metrics', {'inference': elapsed, 'chunk': seconds,
                                'dropped': dropped, 'output_dropped': self.mixer.main.dropped,
                                'level': last_level, 'queue_ms': (started - captured) * 1000})
        except Exception as exc:
            self.notify('error', str(exc))
        finally:
            self.stop_event.set()
            self.notify('stopped', '')
