"""Δοκιμές συνεδριών, δρομολόγησης και προστασίας του ενεργού prompt."""

import asyncio
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    """Φορτώνει modules από Client και Server χωρίς σύγκρουση του πακέτου app."""
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sessions = load_module("terminal_sessions_test", "client/app/terminal_session.py")
routing = load_module("terminal_routing_test", "server/app/websocket/terminal_requests.py")


class FramingTests(unittest.TestCase):
    """Ελέγχει το streaming με κατακερματισμένα πλαίσια και ελληνικό output."""

    def test_footer_at_every_packet_boundary(self):
        transcript = 'Ελληνικό αποτέλεσμα χωρίς newline__MH_test:7:"C:\\Εταιρεία\\Logs"\r\n'
        for position in range(len(transcript)):
            framer = sessions.OutputFramer("__MH_test")
            output = framer.feed(transcript[:position]) + framer.feed(transcript[position:])
            self.assertEqual(output, 'Ελληνικό αποτέλεσμα χωρίς newline')
            self.assertEqual(framer.result, (7, 'C:\\Εταιρεία\\Logs'))

    def test_stream_retains_only_marker_prefix(self):
        framer = sessions.OutputFramer("__MH_test")
        output = ''.join(framer.feed('x' * 4096) for _ in range(30))
        self.assertEqual(len(output) + len(framer.buffer), 4096 * 30)
        self.assertLessEqual(len(framer.buffer), len(framer.token) + 1)

    def test_powershell_command_is_base64_not_interpolated(self):
        shell = sessions.PersistentShell("powershell")
        command = '$test = "Ελλάδα"; Write-Output $test'
        payload = json.loads(shell.script(command, "token"))
        self.assertEqual(sessions.base64.b64decode(payload['command']).decode('utf-8'), command)
        self.assertEqual(payload['token'], "token")


class ProcessTests(unittest.IsolatedAsyncioTestCase):
    """Χρησιμοποιεί πραγματικό process για έλεγχο streaming, ορίων και timeout σε Linux."""

    async def asyncSetUp(self):
        self.shell = sessions.PersistentShell("powershell")
        worker = r'''
import json, sys, time
for line in sys.stdin:
    request = json.loads(line)
    import base64
    command = base64.b64decode(request['command']).decode()
    if command == 'hang':
        time.sleep(60)
    elif command == 'stream':
        print('πρώτο', flush=True)
        time.sleep(.1)
        print('δεύτερο', flush=True)
    else:
        print('x' * 120000, flush=True)
    print(request['token'] + ':0:/persisted', flush=True)
'''
        self.shell.process = await asyncio.create_subprocess_exec(sys.executable, '-u', '-c', worker,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        self.chunks = []

    async def asyncTearDown(self):
        await self.shell.close()

    async def emit(self, text):
        """Κρατά το κείμενο streaming χωρίς εξάρτηση από WebSocket."""
        self.chunks.append(text)

    async def test_streaming_same_process_across_commands(self):
        pid = self.shell.process.pid
        result = await self.shell.execute('stream', self.emit)
        self.assertIn('πρώτο', ''.join(self.chunks))
        self.assertIn('δεύτερο', ''.join(self.chunks))
        self.assertEqual(result['current_directory'], '/persisted')
        self.assertEqual(result['exit_code'], 0)
        self.assertFalse(result['session_closed'])
        await self.shell.execute('stream', self.emit)
        self.assertEqual(self.shell.process.pid, pid)

    async def test_output_limit_keeps_draining_until_footer(self):
        result = await self.shell.execute('large', self.emit)
        output = ''.join(self.chunks)
        self.assertTrue(result['truncated'])
        self.assertLess(len(output), 60200)
        self.assertEqual(result['exit_code'], 0)
        result = await self.shell.execute('stream', self.emit)
        self.assertFalse(result['session_closed'])

    async def test_timeout_closes_process(self):
        self.shell.TIMEOUT = .05
        result = await self.shell.execute('hang', self.emit)
        self.assertEqual(result['exit_code'], 124)
        self.assertTrue(result['session_closed'])
        self.assertIsNotNone(self.shell.process.returncode)

    async def test_stop_unblocks_running_command(self):
        task = asyncio.create_task(self.shell.execute('hang', self.emit))
        await asyncio.sleep(.02)
        self.shell.stopped = True
        await self.shell.close()
        result = await asyncio.wait_for(task, 2)
        self.assertEqual(result['exit_code'], 130)
        self.assertTrue(result['session_closed'])

    async def test_manager_accepts_stop_while_command_task_runs(self):
        manager = sessions.TerminalSessionManager()
        sid, rid = str(uuid4()), str(uuid4())
        manager.sessions[sid] = self.shell
        websocket = Mock()
        websocket.send = AsyncMock()
        payload = {'type':'terminal_session_command', 'session_id':sid, 'request_id':rid, 'command':'hang'}
        await asyncio.wait_for(manager.handle(websocket, payload, 'CLIENT01'), .1)
        self.assertIn(sid, manager.tasks)
        await asyncio.sleep(.02)
        await manager.handle(websocket, {**payload,'type':'terminal_session_stop'}, 'CLIENT01')
        await asyncio.gather(*list(manager.tasks.values()))
        self.assertFalse(manager.tasks)
        self.assertFalse(manager.sessions)
        result = json.loads(websocket.send.call_args.args[0])
        self.assertEqual(result['exit_code'], 130)
        self.assertTrue(result['session_closed'])

    async def test_multiline_is_rejected_before_stdin(self):
        with self.assertRaises(ValueError):
            await self.shell.execute('echo hello\necho second', self.emit)
        self.assertFalse(self.shell.busy)


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    """Ελέγχει ότι άλλος Client ή dashboard δεν αποκτά πρόσβαση στη συνεδρία."""

    async def asyncSetUp(self):
        self.manager = Mock()
        self.manager.client_supports.return_value = True
        self.manager.send_to_client = AsyncMock(return_value=True)
        self.manager.send_to_dashboard = AsyncMock()
        self.router = routing.TerminalRequestRouter(self.manager)
        self.owner, self.other = object(), object()
        self.sid, self.rid = str(uuid4()), str(uuid4())
        self.base = {'session_id': self.sid, 'request_id': self.rid, 'client_code': 'CLIENT01'}
        await self.router.request(self.owner, {**self.base, 'type': 'terminal_session_open', 'shell': 'cmd'})

    async def asyncTearDown(self):
        await self.router.discard_dashboard(self.owner)

    async def ready(self):
        """Ολοκληρώνει την αρχική χειραψία της συνεδρίας."""
        await self.router.result('CLIENT01', {**self.base, 'type': 'terminal_session_result',
            'operation': 'open', 'success': True, 'current_directory': 'C:\\Users\\support'})

    async def test_result_from_wrong_client_is_ignored(self):
        await self.router.result('OTHER', {**self.base, 'type': 'terminal_session_result', 'operation': 'open', 'success': True})
        self.manager.send_to_dashboard.assert_not_awaited()
        self.assertFalse(self.router.sessions[self.sid].ready)

    async def test_other_dashboard_cannot_stop_or_close(self):
        for kind in ('terminal_session_stop', 'terminal_session_close', 'terminal_session_command'):
            self.manager.send_to_client.reset_mock()
            await self.router.request(self.other, {**self.base, 'type': kind, 'command': 'whoami'})
            self.manager.send_to_client.assert_not_awaited()
            self.assertIn(self.sid, self.router.sessions)

    async def test_stream_goes_only_to_owner_and_stale_packets_are_ignored(self):
        await self.ready()
        self.rid = str(uuid4())
        self.base['request_id'] = self.rid
        await self.router.request(self.owner, {**self.base, 'type': 'terminal_session_command', 'command': 'whoami'})
        self.manager.send_to_dashboard.reset_mock()
        await self.router.result('CLIENT01', {**self.base, 'type': 'terminal_session_output', 'text': 'support'})
        self.assertIs(self.manager.send_to_dashboard.call_args.args[0], self.owner)
        self.manager.send_to_dashboard.reset_mock()
        await self.router.result('CLIENT01', {**self.base, 'request_id': str(uuid4()), 'type': 'terminal_session_output', 'text': 'late'})
        self.manager.send_to_dashboard.assert_not_awaited()

    async def test_old_client_is_rejected_immediately(self):
        self.manager.client_supports.return_value = False
        self.manager.send_to_client.reset_mock()
        await self.router.request(self.owner, {**self.base, 'session_id': str(uuid4()), 'type': 'terminal_session_open'})
        self.manager.send_to_client.assert_not_awaited()
        self.assertIn('ενημέρωση', self.manager.send_to_dashboard.call_args.args[1]['message'])

    async def test_dashboard_disconnect_closes_remote_shell(self):
        await self.router.discard_dashboard(self.owner)
        self.assertFalse(self.router.sessions)
        self.assertEqual(self.manager.send_to_client.call_args.args[1]['type'], 'terminal_session_close')

    async def test_client_disconnect_notifies_even_idle_session(self):
        await self.ready()
        self.manager.send_to_dashboard.reset_mock()
        await self.router.discard_client('CLIENT01')
        self.assertFalse(self.router.sessions)
        self.assertEqual(self.manager.send_to_dashboard.call_args.args[1]['request_id'], '')

    async def test_timeout_closes_remote_and_notifies(self):
        await self.router.expire(self.sid)
        self.assertFalse(self.router.sessions)
        self.assertEqual(self.manager.send_to_client.call_args.args[1]['type'], 'terminal_session_close')
        self.assertFalse(self.manager.send_to_dashboard.call_args.args[1]['success'])


@unittest.skipUnless(os.name == 'nt', 'Απαιτεί πραγματικό Windows CMD/PowerShell.')
class WindowsShellTests(unittest.IsolatedAsyncioTestCase):
    """Ελέγχει φάκελο, μεταβλητές, ελληνικά και πραγματικά exit codes στα Windows."""

    async def test_cmd_persists_environment_and_directory(self):
        shell = sessions.PersistentShell('cmd')
        chunks = []
        async def emit(text):
            chunks.append(text)
        try:
            await shell.start()
            await shell.execute('set MH_TEST=MoonHard', emit)
            result = await shell.execute('echo %MH_TEST%', emit)
            self.assertIn('MoonHard', ''.join(chunks))
            self.assertEqual(result['exit_code'], 0)
            result = await shell.execute('cd /d "%TEMP%"', emit)
            self.assertEqual(Path(result['current_directory']).resolve(), Path(os.environ['TEMP']).resolve())
            result = await shell.execute('cmd /c exit 7', emit)
            self.assertEqual(result['exit_code'], 7)
        finally:
            await shell.close()

    async def test_powershell_persists_variable_and_reports_errors(self):
        shell = sessions.PersistentShell('powershell')
        chunks = []
        async def emit(text):
            chunks.append(text)
        try:
            await shell.start()
            await shell.execute('$test = "Ελλάδα"', emit)
            result = await shell.execute('Write-Output $test', emit)
            self.assertIn('Ελλάδα', ''.join(chunks))
            self.assertEqual(result['exit_code'], 0)
            result = await shell.execute('throw "test failure"', emit)
            self.assertEqual(result['exit_code'], 1)
            result = await shell.execute('cmd /c exit 9', emit)
            self.assertEqual(result['exit_code'], 9)
        finally:
            await shell.close()


if __name__ == '__main__':
    unittest.main()
