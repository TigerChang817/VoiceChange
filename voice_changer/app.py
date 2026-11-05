"""Tk desktop controls. All Tk updates stay on the main thread."""
from queue import Queue, Empty, Full
from threading import Thread
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser

from .audio import LocalRVC
from .engine import VoiceEngine
from .launcher import EngineLauncher


class App:
    def __init__(self, root):
        self.root = root
        root.title('VoiceChange · AI 女聲變聲器')
        root.geometry('820x960')
        root.minsize(780, 940)
        self.events = Queue(maxsize=100)
        self.launcher = EngineLauncher()
        self.launching = False
        self.shutdown_started = False
        self.api = LocalRVC()
        self.engine = VoiceEngine(self.api, self.emit)
        self.refreshing = False
        self.closing = False
        self.inputs, self.outputs = [], []
        self.model = tk.StringVar()
        self.input = tk.StringVar()
        self.output = tk.StringVar()
        self.monitor_device = tk.StringVar()
        self.monitor_enabled = False
        self.output_volume = tk.DoubleVar(value=100)
        self.monitor_volume = tk.DoubleVar(value=50)
        self.pitch = tk.IntVar(value=6)
        self.seconds = tk.StringVar(value='128')
        self.status = tk.StringVar(value='首次請選擇 AI 引擎；之後會自動啟動後端。')
        self.metrics = tk.StringVar(value='等待啟動')
        self.warning = tk.StringVar()
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TLabel', font=('Microsoft JhengHei UI', 10))
        style.configure('TButton', padding=8)
        body = ttk.Frame(root, padding=24)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='把你的聲音，換個角色。', font=('Microsoft JhengHei UI', 22, 'bold')).pack(anchor='w')
        ttk.Label(body, text='本機 AI 轉換 · Windows / Discord', foreground='#5865f2').pack(anchor='w', pady=(4, 18))
        engine_controls = ttk.Frame(body)
        engine_controls.pack(fill='x', pady=(0, 8))
        self.choose_engine_button = ttk.Button(engine_controls, text='選擇 AI 引擎', command=self.choose_engine)
        self.choose_engine_button.pack(side='left')
        self.launch_button = ttk.Button(engine_controls, text='啟動 AI 引擎', command=self.launch_engine)
        self.launch_button.pack(side='left', padx=8)
        ttk.Button(engine_controls, text='模型管理', command=lambda: webbrowser.open(self.api.url)).pack(side='left')
        self.input_box = self.combo(body, '麥克風輸入', self.input)
        self.output_box = self.combo(body, 'Discord 輸出裝置（CABLE Input）', self.output)
        self.monitor_box = self.combo(body, '監聽耳機（可不選；開始後可即時開關監聽）', self.monitor_device)
        self.model_box = self.combo(body, '女聲 RVC 模型', self.model)
        row = ttk.Frame(body)
        row.pack(fill='x', pady=8)
        ttk.Label(row, text='音高（半音）').pack(side='left')
        self.pitch_box = ttk.Spinbox(row, from_=-12, to=12, textvariable=self.pitch, width=5, state='readonly')
        self.pitch_box.pack(side='left', padx=10)
        ttk.Label(row, text='音訊區塊（毫秒）').pack(side='left', padx=(24, 0))
        self.seconds_box = ttk.Combobox(row, values=('64', '96', '128', '192', '256'), textvariable=self.seconds, width=5, state='readonly')
        self.seconds_box.pack(side='left', padx=10)
        ttk.Label(body, text='先試 +6 半音，再依模型調整。實際延遲包含區塊、推論與緩衝。', wraplength=700).pack(anchor='w')
        listening = ttk.Frame(body)
        listening.pack(fill='x', pady=8)
        self.monitor_button = ttk.Button(listening, text='監聽：關（點我聽自己）', command=self.toggle_monitor)
        self.monitor_button.pack(side='left')
        self.output_volume_label = tk.StringVar(value='Discord 音量：100%')
        self.monitor_volume_label = tk.StringVar(value='監聽音量：50%')
        for label, variable, maximum in ((self.output_volume_label, self.output_volume, 200),
                                         (self.monitor_volume_label, self.monitor_volume, 100)):
            volume_row = ttk.Frame(body)
            volume_row.pack(fill='x', pady=3)
            ttk.Label(volume_row, textvariable=label, width=23).pack(side='left')
            ttk.Scale(volume_row, from_=0, to=maximum, variable=variable,
                      command=self.update_volume).pack(side='left', fill='x', expand=True)
        controls = ttk.Frame(body)
        controls.pack(fill='x', pady=18)
        self.refresh_button = ttk.Button(controls, text='重新整理裝置 / 模型', command=self.refresh)
        self.refresh_button.pack(side='left')
        self.start_button = ttk.Button(controls, text='開始變聲', command=self.start)
        self.start_button.pack(side='left', padx=10)
        self.stop_button = ttk.Button(controls, text='停止', command=self.stop, state='disabled')
        self.stop_button.pack(side='left')
        ttk.Separator(body).pack(fill='x')
        ttk.Label(body, textvariable=self.status, wraplength=700).pack(anchor='w', pady=(14, 8))
        ttk.Label(body, textvariable=self.metrics, wraplength=700).pack(anchor='w')
        ttk.Label(body, textvariable=self.warning, foreground='#b45309', wraplength=700).pack(anchor='w', pady=8)
        ttk.Label(body, text='Discord：輸入裝置選 CABLE Output，輸出裝置選耳機。\n先關閉 Krisp、降噪、自動增益，再測試音量。停止時輸出靜音，不會回送原聲。', wraplength=700).pack(anchor='w', pady=8)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        self.refresh()
        if self.launcher.saved_executable():
            root.after(500, self.launch_engine)

    def choose_engine(self):
        if self.engine.running or self.launching:
            return
        path = filedialog.askopenfilename(title="選擇 start_http.bat 使用的後端 exe（不要選 client 內的 Demo）", filetypes=[("MMVC 後端", "*.exe")])
        if path:
            self.launch_engine(path)

    def launch_engine(self, path=None):
        if self.engine.running or self.launching or self.closing:
            return
        if self.refreshing:
            self.root.after(200, lambda: self.launch_engine(path))
            return
        path = path or self.launcher.saved_executable()
        if not path:
            self.choose_engine()
            return
        self.launching = True
        self.set_busy(True)
        self.launch_button.config(state="disabled")
        self.choose_engine_button.config(state="disabled")
        self.stop_button.config(state="disabled")
        def work():
            try:
                api = self.launcher.start(path, self.emit)
                self.emit("engine_ready", api)
            except Exception as exc:
                self.emit("engine_failed", str(exc))
        Thread(target=work, daemon=True).start()

    def update_volume(self, _=None):
        output, monitor = self.output_volume.get(), self.monitor_volume.get()
        self.output_volume_label.set(f'Discord 音量：{output:.0f}%')
        self.monitor_volume_label.set(f'監聽音量：{monitor:.0f}%')
        self.engine.mixer.set_volume(output=output / 100, monitor=monitor / 100)

    def toggle_monitor(self):
        if not self.monitor_enabled and self.monitor_box.current() < 0:
            messagebox.showinfo('選擇耳機', '請先選監聽耳機；若正在變聲，請先停止再選裝置。')
            return
        self.monitor_enabled = not self.monitor_enabled
        self.engine.mixer.set_monitor(self.monitor_enabled)
        self.monitor_button.config(text='監聽：開（點我關閉）' if self.monitor_enabled else '監聽：關（點我聽自己）')

    def combo(self, parent, label, variable):
        ttk.Label(parent, text=label).pack(anchor='w', pady=(6, 2))
        box = ttk.Combobox(parent, textvariable=variable, state='readonly')
        box.pack(fill='x')
        return box

    def emit(self, kind, value):
        try:
            self.events.put_nowait((kind, value))
        except Full:
            # Retain lifecycle/error events; discard old callback telemetry.
            if kind in ('error', 'stopped', 'refreshed', 'engine_ready', 'engine_failed', 'shutdown_complete'):
                try:
                    self.events.get_nowait()
                except Empty:
                    pass
                try:
                    self.events.put_nowait((kind, value))
                except Full:
                    pass

    def refresh(self):
        if self.refreshing or self.engine.running or self.launching:
            return
        self.refreshing = True
        self.start_button.config(state='disabled')
        self.refresh_button.config(state='disabled')
        def work():
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                hosts = sd.query_hostapis()
                inputs, outputs = [], []
                for i, device in enumerate(devices):
                    label = f"{i}: {device['name']} [{hosts[device['hostapi']]['name']}]"
                    if device['max_input_channels']:
                        inputs.append((label, i))
                    if device['max_output_channels']:
                        outputs.append((label, i, min(2, device['max_output_channels'])))
                try:
                    models = self.api.models()
                    warning = '' if models else '找不到 RVC 模型：請在即時引擎介面匯入模型，再重新整理。'
                except Exception as exc:
                    models, warning = [], str(exc)
                self.emit('refreshed', (inputs, outputs, models, warning))
            except Exception as exc:
                self.emit('refreshed', ([], [], [], str(exc)))
        Thread(target=work, daemon=True).start()

    def set_busy(self, busy):
        for widget in (self.input_box, self.output_box, self.monitor_box, self.model_box, self.pitch_box, self.seconds_box):
            widget.config(state='disabled' if busy else 'readonly')
        self.start_button.config(state='disabled' if busy else 'normal')
        self.refresh_button.config(state='disabled' if busy else 'normal')
        self.stop_button.config(state='normal' if busy else 'disabled')
        self.launch_button.config(state='disabled' if busy else 'normal')
        self.choose_engine_button.config(state='disabled' if busy else 'normal')

    def start(self):
        if self.engine.running or self.refreshing or self.launching:
            return
        try:
            mic = self.inputs[self.input_box.current()][1] if self.input_box.current() >= 0 else None
            output = self.outputs[self.output_box.current()] if self.output_box.current() >= 0 else None
            if mic is None or output is None or not self.model.get():
                raise ValueError('請選擇麥克風、輸出裝置與模型。')
            monitor = self.outputs[self.monitor_box.current()] if self.monitor_box.current() >= 0 else None
            if self.monitor_enabled and monitor is None:
                raise ValueError('請選擇監聽耳機。')
            if monitor is not None and monitor[1] == output[1]:
                raise ValueError('監聽耳機與 Discord 輸出請選不同裝置，避免聲音重複。')
            self.update_volume()
            self.warning.set('')
            self.set_busy(True)
            self.engine.start(mic, output[1], output[2], float(self.seconds.get()) / 1000, self.model.get(), self.pitch.get(),
                              monitor[1] if monitor else None, monitor[2] if monitor else 2)
        except Exception as exc:
            self.set_busy(False)
            messagebox.showerror('無法開始', str(exc))

    def stop(self):
        self.engine.stop()
        self.status.set('停止中；等待目前推論結束…')
        self.stop_button.config(state='disabled')

    def close(self):
        self.closing = True
        self.launcher.cancel.set()
        self.stop()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind in ('engine_ready', 'engine_failed'):
                    self.launching = False
                    self.set_busy(False)
                    if kind == 'engine_failed':
                        self.warning.set(value)
                    elif value is not None and not self.closing:
                        self.api = value
                        self.engine.api = value
                        self.status.set('AI 引擎已就緒，無需開啟 Demo 視窗。')
                        self.refresh()
                elif kind == 'shutdown_complete':
                    self.root.destroy()
                    return
                elif kind == 'refreshed':
                    self.refreshing = False
                    self.inputs, self.outputs, models, warning = value
                    for box, values in ((self.input_box, [x[0] for x in self.inputs]),
                                        (self.output_box, [x[0] for x in self.outputs]),
                                        (self.monitor_box, [x[0] for x in self.outputs]), (self.model_box, models)):
                        previous = box.get()
                        box['values'] = values
                        box.set(previous if previous in values else '')
                    self.warning.set(warning)
                    self.set_busy(False)
                elif kind == 'status':
                    self.status.set(value)
                elif kind == 'warning':
                    self.warning.set('音效裝置警告：' + value)
                elif kind == 'error':
                    self.warning.set(value)
                elif kind == 'stopped':
                    self.status.set('已停止，輸出靜音。')
                    self.set_busy(False)
                elif kind == 'metrics':
                    self.metrics.set(f"推論往返 {value['inference'] * 1000:.0f}ms / 區塊 {value['chunk'] * 1000:.0f}ms · 排隊 {value['queue_ms']:.0f}ms · 丟棄 {value['dropped']} 區塊 / {value['output_dropped']} 取樣")
                    if value['inference'] > value['chunk']:
                        self.warning.set('推論慢於收音；可能斷續。請加大區塊、關閉其他 GPU 程式或換較小模型。')
        except Empty:
            pass
        if self.closing and not self.engine.running and not self.launching and not self.shutdown_started:
            self.shutdown_started = True
            def shutdown():
                try:
                    self.launcher.stop()
                finally:
                    self.emit('shutdown_complete', '')
            Thread(target=shutdown, daemon=True).start()
        self.root.after(100, self.poll)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
