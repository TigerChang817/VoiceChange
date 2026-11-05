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
        root.geometry('1040x820')
        root.minsize(760, 640)
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
        self.build_interface(root)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        self.refresh()
        if self.launcher.saved_executable():
            root.after(500, self.launch_engine)

    def build_interface(self, root):
        bg, panel, field = '#0d1120', '#191f32', '#11172a'
        text, muted, accent = '#edf1ff', '#9aa8c8', '#8b78ff'
        root.configure(bg=bg)
        root.option_add('*TCombobox*Listbox.background', field)
        root.option_add('*TCombobox*Listbox.foreground', text)
        root.option_add('*TCombobox*Listbox.selectBackground', '#4c4482')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft JhengHei UI', 10), background=panel, foreground=text)
        style.configure('TFrame', background=panel)
        style.configure('Page.TFrame', background=bg)
        style.configure('TLabel', background=panel, foreground=text)
        style.configure('Muted.TLabel', foreground=muted)
        style.configure('Title.TLabel', font=('Segoe UI', 25, 'bold'), background=bg)
        style.configure('Kicker.TLabel', foreground=accent, background=bg, font=('Segoe UI', 9, 'bold'))
        style.configure('Subtitle.TLabel', foreground=muted, background=bg)
        style.configure('Section.TLabel', font=('Microsoft JhengHei UI', 12, 'bold'))
        style.configure('TButton', background='#2a334e', foreground=text, borderwidth=0, padding=(16, 10))
        style.map('TButton', background=[('active', '#3a4665'), ('disabled', '#20273c')],
                  foreground=[('disabled', '#65718e')])
        style.configure('Primary.TButton', background='#7865ed', font=('Microsoft JhengHei UI', 11, 'bold'))
        style.map('Primary.TButton', background=[('active', '#917eff'), ('disabled', '#373453')])
        style.configure('MonitorOn.TButton', background='#145d55', foreground='#b1ffdf')
        style.map('MonitorOn.TButton', background=[('active', '#207a6e')])
        for widget in ('TCombobox', 'TSpinbox'):
            style.configure(widget, fieldbackground=field, background='#2b3550', foreground=text,
                            arrowcolor=muted, bordercolor='#303c59', padding=8)
            style.map(widget, fieldbackground=[('readonly', field), ('disabled', '#22283a')],
                      foreground=[('readonly', text), ('disabled', '#65718e')], selectbackground=[('readonly', field)])
        style.configure('Horizontal.TScale', background=panel, troughcolor=field, sliderlength=18)
        style.configure('TSeparator', background='#303b55')
        header = ttk.Frame(root, style='Page.TFrame', padding=(28, 20, 28, 12))
        header.pack(fill='x')
        ttk.Label(header, text='YOUR VOICE, REIMAGINED', style='Kicker.TLabel').pack(anchor='w')
        ttk.Label(header, text='VoiceChange', style='Title.TLabel').pack(anchor='w', pady=(2, 2))
        ttk.Label(header, text='換一種聲線，保持你的節奏。', style='Subtitle.TLabel').pack(anchor='w')

        # Keep start/stop and live status visible even on smaller screens.
        footer = ttk.Frame(root, padding=(24, 14))
        footer.pack(side='bottom', fill='x', padx=24, pady=(8, 20))
        actions = ttk.Frame(footer)
        actions.pack(fill='x')
        self.start_button = ttk.Button(actions, text='開始變聲', style='Primary.TButton', command=self.start)
        self.start_button.pack(side='right')
        self.stop_button = ttk.Button(actions, text='停止', command=self.stop, state='disabled')
        self.stop_button.pack(side='right', padx=10)
        self.refresh_button = ttk.Button(actions, text='重新整理', command=self.refresh)
        self.refresh_button.pack(side='left')
        ttk.Label(footer, textvariable=self.status, wraplength=680).pack(anchor='w', pady=(12, 3))
        ttk.Label(footer, textvariable=self.metrics, style='Muted.TLabel', wraplength=680).pack(anchor='w')
        ttk.Label(footer, textvariable=self.warning, foreground='#ffc98a', wraplength=680).pack(anchor='w', pady=(3, 0))

        viewport = ttk.Frame(root, style='Page.TFrame')
        viewport.pack(fill='both', expand=True, padx=24)
        canvas = tk.Canvas(viewport, bg=bg, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(viewport, orient='vertical', command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        content = ttk.Frame(canvas, style='Page.TFrame')
        window = canvas.create_window((0, 0), window=content, anchor='nw')
        content.columnconfigure(0, weight=1, uniform='cards')
        content.columnconfigure(1, weight=1, uniform='cards')
        content.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        self.engine_card = ttk.Frame(content, padding=20)
        self.engine_card.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 14))
        self.section(self.engine_card, '01  AI 引擎', '首次選擇後端，之後自動啟動。')
        engine_controls = ttk.Frame(self.engine_card)
        engine_controls.pack(fill='x', pady=(12, 0))
        self.choose_engine_button = ttk.Button(engine_controls, text='選擇 AI 引擎', command=self.choose_engine)
        self.choose_engine_button.pack(side='left')
        self.launch_button = ttk.Button(engine_controls, text='啟動引擎', command=self.launch_engine)
        self.launch_button.pack(side='left', padx=8)
        ttk.Button(engine_controls, text='模型管理', command=lambda: webbrowser.open(self.api.url)).pack(side='left')

        self.route_card = ttk.Frame(content, padding=20)
        self.route_card.grid(row=1, column=0, sticky='nsew', padx=(0, 7))
        self.section(self.route_card, '02  聲音路由', '麥克風 → AI 變聲 → Discord / 耳機')
        self.input_box = self.combo(self.route_card, '麥克風輸入', self.input)
        self.output_box = self.combo(self.route_card, 'Discord 輸出 · CABLE Input', self.output)
        self.monitor_box = self.combo(self.route_card, '監聽耳機 · 可選', self.monitor_device)
        ttk.Label(self.route_card, text='Discord 輸入請選 CABLE Output。\n輸出請選耳機，避免回音。',
                  style='Muted.TLabel', wraplength=350).pack(anchor='w', pady=(16, 0))

        self.voice_card = ttk.Frame(content, padding=20)
        self.voice_card.grid(row=1, column=1, sticky='nsew', padx=(7, 0))
        self.section(self.voice_card, '03  聲線與監聽', '用耳機試聽，找到舒服的聲音。')
        self.model_box = self.combo(self.voice_card, '女聲 RVC 模型', self.model)
        tuning = ttk.Frame(self.voice_card)
        tuning.pack(fill='x', pady=(14, 12))
        left, right = ttk.Frame(tuning), ttk.Frame(tuning)
        left.pack(side='left', fill='x', expand=True)
        right.pack(side='left', fill='x', expand=True, padx=(16, 0))
        ttk.Label(left, text='音高 · 半音', style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
        self.pitch_box = ttk.Spinbox(left, from_=-12, to=12, textvariable=self.pitch, width=7, state='readonly')
        self.pitch_box.pack(fill='x')
        ttk.Label(right, text='區塊 · 毫秒', style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
        self.seconds_box = ttk.Combobox(right, values=('64', '96', '128', '192', '256'),
                                       textvariable=self.seconds, width=7, state='readonly')
        self.seconds_box.pack(fill='x')
        self.monitor_button = ttk.Button(self.voice_card, text='監聽已關閉 · 點我聽自己', command=self.toggle_monitor)
        self.monitor_button.pack(fill='x', pady=(0, 12))
        self.output_volume_label = tk.StringVar(value='Discord 音量：100%')
        self.monitor_volume_label = tk.StringVar(value='監聽音量：50%')
        for label, variable, maximum in ((self.output_volume_label, self.output_volume, 200),
                                        (self.monitor_volume_label, self.monitor_volume, 100)):
            ttk.Label(self.voice_card, textvariable=label, style='Muted.TLabel').pack(anchor='w')
            ttk.Scale(self.voice_card, from_=0, to=maximum, variable=variable,
                      command=self.update_volume).pack(fill='x', pady=(5, 12))
        self._layout_columns = 2
        def resize(event):
            canvas.itemconfigure(window, width=event.width)
            columns = 2 if event.width >= 860 else 1
            if columns != self._layout_columns:
                self._layout_columns = columns
                self.route_card.grid_configure(columnspan=2 if columns == 1 else 1,
                                               padx=(0, 0) if columns == 1 else (0, 7))
                self.voice_card.grid_configure(row=2 if columns == 1 else 1, column=0 if columns == 1 else 1,
                    columnspan=2 if columns == 1 else 1, padx=(0, 0) if columns == 1 else (7, 0),
                    pady=(14, 0) if columns == 1 else (0, 0))
            for widget in footer.winfo_children():
                if isinstance(widget, ttk.Label):
                    widget.configure(wraplength=max(350, event.width - 55))
        canvas.bind('<Configure>', resize)
        def wheel(event):
            if event.widget.winfo_class() not in ('TCombobox', 'TSpinbox', 'TScale'):
                canvas.yview_scroll(-int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1), 'units')
        root.bind('<MouseWheel>', wheel)
        canvas.bind('<Button-4>', lambda event: canvas.yview_scroll(-1, 'units'))
        canvas.bind('<Button-5>', lambda event: canvas.yview_scroll(1, 'units'))

    @staticmethod
    def section(parent, title, subtitle):
        ttk.Label(parent, text=title, style='Section.TLabel').pack(anchor='w')
        ttk.Label(parent, text=subtitle, style='Muted.TLabel', wraplength=350).pack(anchor='w', pady=(5, 4))

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
        self.monitor_button.config(text='監聽已開啟 · 點我關閉' if self.monitor_enabled else '監聽已關閉 · 點我聽自己',
                                   style='MonitorOn.TButton' if self.monitor_enabled else 'TButton')

    def combo(self, parent, label, variable):
        ttk.Label(parent, text=label, style='Muted.TLabel').pack(anchor='w', pady=(12, 5))
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
