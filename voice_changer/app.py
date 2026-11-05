"""Tk desktop controls. All Tk updates stay on the main thread."""
from queue import Queue, Empty, Full
from threading import Thread
import tkinter as tk
from tkinter import ttk, messagebox

from .audio import LocalRVC
from .engine import VoiceEngine


class App:
    def __init__(self, root):
        self.root = root
        root.title('Time Killer · AI 女聲變聲器')
        root.geometry('780x640')
        root.minsize(720, 600)
        self.events = Queue(maxsize=100)
        self.api = LocalRVC()
        self.engine = VoiceEngine(self.api, self.emit)
        self.refreshing = False
        self.closing = False
        self.inputs, self.outputs = [], []
        self.model = tk.StringVar()
        self.input = tk.StringVar()
        self.output = tk.StringVar()
        self.pitch = tk.IntVar(value=6)
        self.seconds = tk.StringVar(value='128')
        self.status = tk.StringVar(value='請先啟動即時引擎並載入女聲模型，再重新整理。')
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
        self.input_box = self.combo(body, '麥克風輸入', self.input)
        self.output_box = self.combo(body, '輸出裝置（Discord 選 CABLE Input；試聽選耳機）', self.output)
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
            if kind in ('error', 'stopped', 'refreshed'):
                try:
                    self.events.get_nowait()
                except Empty:
                    pass
                try:
                    self.events.put_nowait((kind, value))
                except Full:
                    pass

    def refresh(self):
        if self.refreshing or self.engine.running:
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
        for widget in (self.input_box, self.output_box, self.model_box, self.pitch_box, self.seconds_box):
            widget.config(state='disabled' if busy else 'readonly')
        self.start_button.config(state='disabled' if busy else 'normal')
        self.refresh_button.config(state='disabled' if busy else 'normal')
        self.stop_button.config(state='normal' if busy else 'disabled')

    def start(self):
        if self.engine.running or self.refreshing:
            return
        try:
            mic = self.inputs[self.input_box.current()][1] if self.input_box.current() >= 0 else None
            output = self.outputs[self.output_box.current()] if self.output_box.current() >= 0 else None
            if mic is None or output is None or not self.model.get():
                raise ValueError('請選擇麥克風、輸出裝置與模型。')
            self.warning.set('')
            self.set_busy(True)
            self.engine.start(mic, output[1], output[2], float(self.seconds.get()) / 1000, self.model.get(), self.pitch.get())
        except Exception as exc:
            self.set_busy(False)
            messagebox.showerror('無法開始', str(exc))

    def stop(self):
        self.engine.stop()
        self.status.set('停止中；等待目前推論結束…')
        self.stop_button.config(state='disabled')

    def close(self):
        self.closing = True
        self.stop()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'refreshed':
                    self.refreshing = False
                    self.inputs, self.outputs, models, warning = value
                    for box, values in ((self.input_box, [x[0] for x in self.inputs]),
                                        (self.output_box, [x[0] for x in self.outputs]), (self.model_box, models)):
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
        if self.closing and not self.engine.running:
            self.root.destroy()
            return
        self.root.after(100, self.poll)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
