"""Launch only the MMVC backend, using verified local TLS (no Demo client)."""
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Lock
import time

from .audio import LocalRVC

IS_WINDOWS = sys.platform == 'win32'


def settings_dir():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'VoiceChange'


def create_certificate(directory):
    """A private local trust anchor with localhost SAN; verification stays on."""
    from datetime import datetime, timedelta, timezone
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = directory / 'localhost.pem', directory / 'localhost-key.pem'
    if cert_path.exists() and key_path.exists():
        certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())
        if certificate.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=1):
            return cert_path, key_path
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'VoiceChange localhost')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),
                       x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256()))
    # The private key is local runtime state, never part of the repository.
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key_path.chmod(0o600)
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def backend_command(executable, certificate, key):
    return [str(executable), '-p', '18889', '--https', 'true',
            '--httpsSelfSigned', 'false', '--httpsKey', str(key), '--httpsCert', str(certificate)]


class EngineLauncher:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else settings_dir()
        self.process = None
        self.log = None
        self.cancel = Event()
        self.lock = Lock()

    def saved_executable(self):
        try:
            return json.loads((self.directory / 'engine.json').read_text(encoding='utf-8'))['executable']
        except (OSError, ValueError, KeyError):
            return ''

    def start(self, executable, notify):
        if not IS_WINDOWS:
            raise RuntimeError('整合引擎啟動目前只支援 Windows。')
        executable = Path(executable).resolve()
        if not executable.is_file() or executable.suffix.lower() != '.exe':
            raise ValueError('請選擇解壓縮引擎包內的後端 MMVCServerSIO.exe')
        self.cancel.clear()
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError('引擎正在啟動或執行中')
        flags = subprocess.CREATE_NO_WINDOW
        # Electron's client has the same filename in some packages: verify help
        # before trusting it as a backend. Never rewrite upstream engine files.
        notify('status', '確認引擎執行檔…')
        try:
            probe = subprocess.run([str(executable), '--help'], cwd=executable.parent,
                capture_output=True, timeout=20, creationflags=flags)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('這可能是 Demo 客戶端；請選 start_http.bat 所呼叫的後端 exe。') from exc
        help_text = (probe.stdout + probe.stderr).decode('utf-8', errors='replace')
        if probe.returncode != 0 or '--httpsSelfSigned' not in help_text:
            raise ValueError('不是相容的 MMVC 後端。請選 start_http.bat 所呼叫的 exe，不是 client 資料夾內的 Demo。')
        certificate, key = create_certificate(self.directory)
        api = LocalRVC(port=18889, cafile=certificate)
        self.log = (self.directory / 'engine.log').open('ab')
        with self.lock:
            if self.cancel.is_set():
                self.log.close()
                return None
            try:
                self.process = subprocess.Popen(backend_command(executable, certificate, key),
                    cwd=executable.parent, stdout=self.log, stderr=subprocess.STDOUT,
                    creationflags=flags)
            except Exception:
                self.log.close()
                raise
        (self.directory / 'engine.json').write_text(json.dumps({'executable': str(executable)}), encoding='utf-8')
        notify('status', 'AI 引擎啟動中，首次下載模型可能需要數分鐘…')
        deadline = time.monotonic() + 300
        while not self.cancel.wait(.5):
            if self.process.poll() is not None:
                self.log.close()
                raise RuntimeError(f'引擎提前結束。請查看 {self.directory / "engine.log"}')
            try:
                api.models(timeout=2)
                return api
            except Exception:
                if time.monotonic() >= deadline:
                    self.stop()
                    raise RuntimeError(f'等待引擎逾時。請查看 {self.directory / "engine.log"}')
        self.stop()
        return None

    def stop(self):
        self.cancel.set()
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                if IS_WINDOWS:
                    subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                        capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    self.process.terminate()
                self.process.wait(timeout=10)
            if self.log is not None:
                self.log.close()
