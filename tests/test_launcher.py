from pathlib import Path
import ssl
import tempfile
import unittest

from voice_changer.launcher import create_certificate, backend_command, EngineLauncher
from voice_changer.audio import LocalRVC


class LauncherTests(unittest.TestCase):
    def test_backend_command_uses_https_without_demo_or_shell(self):
        command = backend_command(Path('D:/engine/MMVCServerSIO.exe'), Path('cert.pem'), Path('key.pem'))
        self.assertEqual(command[1:5], ['-p', '18889', '--https', 'true'])
        self.assertEqual(command[5:7], ['--httpsSelfSigned', 'false'])
        self.assertNotIn('cmd', command)

    def test_local_certificate_is_reused_and_tls_verification_stays_enabled(self):
        from cryptography import x509
        import ipaddress
        with tempfile.TemporaryDirectory() as directory:
            cert, key = create_certificate(directory)
            first = cert.read_bytes()
            self.assertEqual(create_certificate(directory), (cert, key))
            self.assertEqual(cert.read_bytes(), first)
            certificate = x509.load_pem_x509_certificate(first)
            san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            self.assertIn(ipaddress.ip_address('127.0.0.1'), san.get_values_for_type(x509.IPAddress))
            api = LocalRVC(port=18889, cafile=cert)
            handler = next(h for h in api.opener.handlers if hasattr(h, '_context'))
            self.assertEqual(handler._context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(handler._context.check_hostname)
            self.assertEqual(api.url, 'https://127.0.0.1:18889')

    def test_stop_does_not_terminate_external_engines(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = EngineLauncher(directory)
            self.assertEqual(launcher.saved_executable(), '')
            launcher.stop()
            self.assertTrue(launcher.cancel.is_set())
            self.assertIsNone(launcher.process)

    def test_windows_launch_probes_backend_and_waits_for_ready(self):
        from unittest.mock import Mock, patch
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            executable = (Path(directory) / 'MMVCServerSIO.exe').resolve()
            executable.touch()
            launcher = EngineLauncher(Path(directory) / 'settings')
            api = Mock()
            process = Mock(pid=1234)
            process.poll.return_value = None
            probe = subprocess.CompletedProcess([], 0, b'--httpsSelfSigned', b'')
            with patch('voice_changer.launcher.IS_WINDOWS', True), \
                 patch('voice_changer.launcher.subprocess.CREATE_NO_WINDOW', 0, create=True), \
                 patch('voice_changer.launcher.subprocess.run', return_value=probe) as run, \
                 patch('voice_changer.launcher.subprocess.Popen', return_value=process) as popen, \
                 patch('voice_changer.launcher.LocalRVC', return_value=api), \
                 patch.object(launcher.cancel, 'wait', return_value=False):
                result = launcher.start(executable, Mock())
                try:
                    self.assertIs(result, api)
                    self.assertEqual(Path(launcher.saved_executable()).resolve(), executable.resolve())
                    command = popen.call_args.args[0]
                    self.assertIn('--https', command)
                    self.assertEqual(popen.call_args.kwargs['cwd'], executable.parent.resolve())
                    self.assertNotIn('shell', popen.call_args.kwargs)
                finally:
                    launcher.stop()
                self.assertEqual(run.call_args.args[0], ['taskkill', '/PID', '1234', '/T', '/F'])
                process.wait.assert_called_once()

    def test_incompatible_client_is_rejected_without_starting_backend(self):
        from unittest.mock import Mock, patch
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'client.exe'
            executable.touch()
            launcher = EngineLauncher(directory)
            probe = subprocess.CompletedProcess([], 0, b'Electron', b'')
            with patch('voice_changer.launcher.IS_WINDOWS', True), \
                 patch('voice_changer.launcher.subprocess.CREATE_NO_WINDOW', 0, create=True), \
                 patch('voice_changer.launcher.subprocess.run', return_value=probe), \
                 patch('voice_changer.launcher.subprocess.Popen') as popen:
                with self.assertRaisesRegex(ValueError, '不是相容'):
                    launcher.start(executable, Mock())
                popen.assert_not_called()
