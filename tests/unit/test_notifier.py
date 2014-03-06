# Copyright 2014 Rackspace
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import io
import signal
import sys
import unittest

import mock

from heyu import notifier
from heyu import protocol
from heyu import util


class TestException(Exception):
    pass


class NotifierServerTest(unittest.TestCase):
    def _signal_test(self, notifier_server, mock_signal):
        signals = [
            mock.call(signal.SIGINT, notifier_server.stop),
            mock.call(signal.SIGTERM, notifier_server.stop),
        ]
        if hasattr(signal, 'SIGUSR1'):
            signals.append(mock.call(signal.SIGUSR1, notifier_server.shutdown))
        mock_signal.assert_has_calls(signals)
        self.assertEqual(len(signals), mock_signal.call_count)

    @mock.patch.object(sys, 'argv', ['/bin/notifier.py'])
    @mock.patch('tendril.get_manager', return_value='manager')
    @mock.patch('gevent.signal')
    @mock.patch('uuid.uuid4', return_value='some-uuid')
    @mock.patch('gevent.event.Event', return_value='event')
    @mock.patch.object(util, 'cert_wrapper', return_value='wrapper')
    @mock.patch.object(util, 'outgoing_endpoint', return_value='endpoint')
    def test_init_basic(self, mock_outgoing_endpoint, mock_cert_wrapper,
                        mock_Event, mock_uuid4, mock_signal, mock_get_manager):
        result = notifier.NotifierServer('hub')

        self.assertEqual('hub', result._hub)
        self.assertEqual('manager', result._manager)
        self.assertEqual('wrapper', result._wrapper)
        self.assertEqual('notifier.py', result._app_name)
        self.assertEqual('some-uuid', result._app_id)
        self.assertEqual(None, result._hub_app)
        self.assertEqual([], result._notifications)
        self.assertEqual('event', result._notify_event)
        mock_outgoing_endpoint.assert_called_once_with('hub')
        mock_get_manager.assert_called_once_with('tcp', 'endpoint')
        mock_cert_wrapper.assert_called_once_with(
            None, 'notifier', secure=True)
        self._signal_test(result, mock_signal)

    @mock.patch.object(sys, 'argv', ['/bin/notifier.py'])
    @mock.patch('tendril.get_manager', return_value='manager')
    @mock.patch('gevent.signal')
    @mock.patch('uuid.uuid4', return_value='some-uuid')
    @mock.patch('gevent.event.Event', return_value='event')
    @mock.patch.object(util, 'cert_wrapper', return_value='wrapper')
    @mock.patch.object(util, 'outgoing_endpoint', return_value='endpoint')
    def test_init_alt(self, mock_outgoing_endpoint, mock_cert_wrapper,
                      mock_Event, mock_uuid4, mock_signal, mock_get_manager):
        result = notifier.NotifierServer('hub', 'cert_conf', False, 'app',
                                         'app-uuid')

        self.assertEqual('hub', result._hub)
        self.assertEqual('manager', result._manager)
        self.assertEqual('wrapper', result._wrapper)
        self.assertEqual('app', result._app_name)
        self.assertEqual('app-uuid', result._app_id)
        self.assertEqual(None, result._hub_app)
        self.assertEqual([], result._notifications)
        self.assertEqual('event', result._notify_event)
        mock_outgoing_endpoint.assert_called_once_with('hub')
        mock_get_manager.assert_called_once_with('tcp', 'endpoint')
        mock_cert_wrapper.assert_called_once_with(
            'cert_conf', 'notifier', secure=False)
        self._signal_test(result, mock_signal)

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    @mock.patch.object(notifier.NotifierServer, 'start')
    def test_iter_running(self, mock_start, mock_init):
        server = notifier.NotifierServer()
        server._hub_app = 'application'

        result = iter(server)

        self.assertEqual(server, result)
        self.assertFalse(mock_start.called)

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    @mock.patch.object(notifier.NotifierServer, 'start')
    def test_iter_nonrunning(self, mock_start, mock_init):
        server = notifier.NotifierServer()
        server._hub_app = None

        result = iter(server)

        self.assertEqual(server, result)
        mock_start.assert_called_once_with()

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    @mock.patch.object(sys, 'exit', side_effect=TestException())
    def test_next_notification(self, mock_exit, mock_init):
        server = notifier.NotifierServer()
        server._notifications = ['notification']
        server._notify_event = mock.Mock()
        server._hub_app = None

        result = server.next()

        self.assertEqual('notification', result)
        self.assertEqual(0, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    @mock.patch.object(sys, 'exit', side_effect=TestException())
    def test_next_exit(self, mock_exit, mock_init):
        server = notifier.NotifierServer()
        server._notifications = [None]
        server._notify_event = mock.Mock()
        server._hub_app = None

        self.assertRaises(TestException, server.next)
        mock_exit.assert_called_once_with()
        self.assertEqual(0, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    @mock.patch.object(sys, 'exit', side_effect=TestException())
    def test_next_empty_stop(self, mock_exit, mock_init):
        server = notifier.NotifierServer()
        server._notifications = []
        server._notify_event = mock.Mock()
        server._hub_app = None

        self.assertRaises(StopIteration, server.next)
        server._notify_event.assert_has_calls([
            mock.call.clear(),
        ])
        self.assertEqual(1, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    @mock.patch.object(sys, 'exit', side_effect=TestException())
    def test_next_empty_loop(self, mock_exit, mock_init):
        server = notifier.NotifierServer()
        server._notifications = []
        server._notify_event = mock.Mock()
        server._hub_app = 'app'

        def fake_wait():
            server._notifications.append('waited')
        server._notify_event.wait.side_effect = fake_wait

        result = server.next()

        self.assertEqual('waited', result)
        server._notify_event.assert_has_calls([
            mock.call.clear(),
            mock.call.wait(),
        ])
        self.assertEqual(2, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    @mock.patch.object(notifier, 'NotifierApplication', return_value='app')
    def test_acceptor(self, mock_NotifierApplication, mock_init):
        server = notifier.NotifierServer()
        server._hub_app = True
        server._app_name = 'app_name'
        server._app_id = 'app_id'

        result = server._acceptor('tendril')

        self.assertEqual('app', result)
        mock_NotifierApplication.assert_called_once_with(
            'tendril', server, 'app_name', 'app_id')

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    def test_start_running(self, mock_init):
        server = notifier.NotifierServer()
        server._hub_app = 'running'
        server._manager = mock.Mock()
        server._hub = 'hub'
        server._wrapper = 'wrapper'

        self.assertRaises(ValueError, server.start)
        self.assertEqual('running', server._hub_app)
        self.assertEqual(0, len(server._manager.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    def test_start_stopped(self, mock_init):
        server = notifier.NotifierServer()
        server._hub_app = None
        server._manager = mock.Mock()
        server._hub = 'hub'
        server._wrapper = 'wrapper'

        server.start()

        self.assertEqual(True, server._hub_app)
        server._manager.assert_has_calls([
            mock.call.start(),
            mock.call.connect('hub', server._acceptor, 'wrapper'),
        ])
        self.assertEqual(2, len(server._manager.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    def test_stop_stopped(self, mock_init):
        server = notifier.NotifierServer()
        server._hub_app = None
        server._manager = mock.Mock()
        server._notifications = []
        server._notify_event = mock.Mock()

        server.stop()

        self.assertEqual(None, server._hub_app)
        self.assertEqual([], server._notifications)
        self.assertEqual(0, len(server._manager.method_calls))
        self.assertEqual(0, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    def test_stop_simple(self, mock_init):
        app = mock.Mock()
        server = notifier.NotifierServer()
        server._hub_app = app
        server._manager = mock.Mock()
        server._notifications = []
        server._notify_event = mock.Mock()

        server.stop()

        self.assertEqual(None, server._hub_app)
        self.assertEqual([], server._notifications)
        server._manager.stop.assert_called_once_with()
        self.assertEqual(1, len(server._manager.method_calls))
        app.disconnect.assert_called_once_with()
        self.assertEqual(1, len(app.method_calls))
        server._notify_event.set.assert_called_once_with()
        self.assertEqual(1, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    def test_stop_connecting(self, mock_init):
        server = notifier.NotifierServer()
        server._hub_app = True
        server._manager = mock.Mock()
        server._notifications = []
        server._notify_event = mock.Mock()

        server.stop()

        self.assertEqual(None, server._hub_app)
        self.assertEqual([], server._notifications)
        server._manager.stop.assert_called_once_with()
        self.assertEqual(1, len(server._manager.method_calls))
        server._notify_event.set.assert_called_once_with()
        self.assertEqual(1, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    def test_stop_sentinel(self, mock_init):
        app = mock.Mock()
        server = notifier.NotifierServer()
        server._hub_app = app
        server._manager = mock.Mock()
        server._notifications = []
        server._notify_event = mock.Mock()

        server.stop('signal', 'arguments')

        self.assertEqual(None, server._hub_app)
        self.assertEqual([None], server._notifications)
        server._manager.stop.assert_called_once_with()
        self.assertEqual(1, len(server._manager.method_calls))
        app.disconnect.assert_called_once_with()
        self.assertEqual(1, len(app.method_calls))
        server._notify_event.set.assert_called_once_with()
        self.assertEqual(1, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    def test_shutdown_stopped(self, mock_init):
        server = notifier.NotifierServer()
        server._hub_app = None
        server._manager = mock.Mock()
        server._notifications = []
        server._notify_event = mock.Mock()

        server.shutdown()

        self.assertEqual(None, server._hub_app)
        self.assertEqual([], server._notifications)
        self.assertEqual(0, len(server._manager.method_calls))
        self.assertEqual(0, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    def test_shutdown_running(self, mock_init):
        server = notifier.NotifierServer()
        server._hub_app = 'running'
        server._manager = mock.Mock()
        server._notifications = []
        server._notify_event = mock.Mock()

        server.shutdown()

        self.assertEqual(None, server._hub_app)
        self.assertEqual([None], server._notifications)
        server._manager.shutdown.assert_called_once_with()
        self.assertEqual(1, len(server._manager.method_calls))
        server._notify_event.set.assert_called_once_with()
        self.assertEqual(1, len(server._notify_event.method_calls))

    @mock.patch.object(notifier.NotifierServer, '__init__', return_value=None)
    def test_notify(self, mock_init):
        server = notifier.NotifierServer()
        server._notifications = []
        server._notify_event = mock.Mock()

        server.notify('notification')

        self.assertEqual(['notification'], server._notifications)
        server._notify_event.set.assert_called_once_with()
        self.assertEqual(1, len(server._notify_event.method_calls))


class NotifierApplicationTest(unittest.TestCase):
    @mock.patch('tendril.Application.__init__', return_value=None)
    @mock.patch('tendril.COBSFramer', return_value='framer')
    @mock.patch.object(protocol, 'Message', return_value=mock.Mock(**{
        'to_frame.return_value': 'some frame',
    }))
    @mock.patch.object(notifier.NotifierApplication, 'send_frame')
    def test_init(self, mock_send_frame, mock_Message,
                  mock_COBSFramer, mock_init):
        parent = mock.Mock()
        result = notifier.NotifierApplication(parent, 'server',
                                              'app_name', 'app_id')

        self.assertEqual('server', result.server)
        self.assertEqual('app_name', result.app_name)
        self.assertEqual('app_id', result.app_id)
        self.assertEqual('framer', parent.framers)
        mock_init.assert_called_once_with(parent)
        mock_COBSFramer.assert_called_once_with(True)
        mock_Message.assert_called_once_with('subscribe')
        mock_Message.return_value.to_frame.assert_called_once_with()
        mock_send_frame.assert_called_once_with('some frame')

    @mock.patch.object(protocol.Message, 'from_frame',
                       side_effect=ValueError('failed to decode'))
    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    @mock.patch.object(notifier.NotifierApplication, 'notify')
    @mock.patch.object(notifier.NotifierApplication, 'disconnect')
    @mock.patch.object(notifier.NotifierApplication, 'closed')
    def test_recv_frame_decodeerror(self, mock_closed, mock_disconnect,
                                    mock_notify, mock_init, mock_from_frame):
        app = notifier.NotifierApplication()
        app.server = mock.Mock()

        app.recv_frame('test')

        mock_from_frame.assert_called_once_with('test')
        mock_notify.assert_called_once_with(
            'Failed To Parse Server Message',
            'Unable to parse a message from the server: failed to decode',
            notifier.ERROR)
        mock_disconnect.assert_called_once_with()
        self.assertFalse(mock_closed.called)
        app.server.stop.assert_called_once_with()
        self.assertFalse(app.server.notify.called)

    @mock.patch.object(protocol.Message, 'from_frame', return_value=mock.Mock(
        msg_type='unknown'))
    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    @mock.patch.object(notifier.NotifierApplication, 'notify')
    @mock.patch.object(notifier.NotifierApplication, 'disconnect')
    @mock.patch.object(notifier.NotifierApplication, 'closed')
    def test_recv_frame_unknownmsg(self, mock_closed, mock_disconnect,
                                   mock_notify, mock_init, mock_from_frame):
        app = notifier.NotifierApplication()
        app.server = mock.Mock()

        app.recv_frame('test')

        mock_from_frame.assert_called_once_with('test')
        mock_notify.assert_called_once_with(
            'Unknown Server Message',
            'An unrecognized server message of type "unknown" was received.',
            notifier.ERROR)
        self.assertFalse(mock_disconnect.called)
        self.assertFalse(mock_closed.called)
        self.assertFalse(app.server.stop.called)
        self.assertFalse(app.server.notify.called)

    @mock.patch.object(protocol.Message, 'from_frame', return_value=mock.Mock(
        msg_type='error', reason='some error'))
    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    @mock.patch.object(notifier.NotifierApplication, 'notify')
    @mock.patch.object(notifier.NotifierApplication, 'disconnect')
    @mock.patch.object(notifier.NotifierApplication, 'closed')
    def test_recv_frame_error(self, mock_closed, mock_disconnect,
                              mock_notify, mock_init, mock_from_frame):
        app = notifier.NotifierApplication()
        app.server = mock.Mock()

        app.recv_frame('test')

        mock_from_frame.assert_called_once_with('test')
        mock_notify.assert_called_once_with(
            'Communication Error',
            'An error occurred communicating with the HeyU hub: some error',
            notifier.ERROR)
        mock_disconnect.assert_called_once_with()
        self.assertFalse(mock_closed.called)
        app.server.stop.assert_called_once_with()
        self.assertFalse(app.server.notify.called)

    @mock.patch.object(protocol.Message, 'from_frame', return_value=mock.Mock(
        msg_type='goodbye'))
    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    @mock.patch.object(notifier.NotifierApplication, 'notify')
    @mock.patch.object(notifier.NotifierApplication, 'disconnect')
    @mock.patch.object(notifier.NotifierApplication, 'closed')
    def test_recv_frame_goodbye(self, mock_closed, mock_disconnect,
                                mock_notify, mock_init, mock_from_frame):
        app = notifier.NotifierApplication()
        app.server = mock.Mock()

        app.recv_frame('test')

        mock_from_frame.assert_called_once_with('test')
        self.assertFalse(mock_notify.called)
        mock_disconnect.assert_called_once_with()
        mock_closed.assert_called_once_with(None)
        self.assertFalse(app.server.stop.called)
        self.assertFalse(app.server.notify.called)

    @mock.patch.object(protocol.Message, 'from_frame', return_value=mock.Mock(
        msg_type='subscribed'))
    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    @mock.patch.object(notifier.NotifierApplication, 'notify')
    @mock.patch.object(notifier.NotifierApplication, 'disconnect')
    @mock.patch.object(notifier.NotifierApplication, 'closed')
    def test_recv_frame_subscribed(self, mock_closed, mock_disconnect,
                                   mock_notify, mock_init, mock_from_frame):
        app = notifier.NotifierApplication()
        app.server = mock.Mock()

        app.recv_frame('test')

        mock_from_frame.assert_called_once_with('test')
        mock_notify.assert_called_once_with(
            'Connection Established',
            'The connection to the HeyU hub has been established.',
            notifier.CONNECTED)
        self.assertFalse(mock_disconnect.called)
        self.assertFalse(mock_closed.called)
        self.assertFalse(app.server.stop.called)
        self.assertFalse(app.server.notify.called)

    @mock.patch.object(protocol.Message, 'from_frame', return_value=mock.Mock(
        msg_type='notify'))
    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    @mock.patch.object(notifier.NotifierApplication, 'notify')
    @mock.patch.object(notifier.NotifierApplication, 'disconnect')
    @mock.patch.object(notifier.NotifierApplication, 'closed')
    def test_recv_frame_notify(self, mock_closed, mock_disconnect,
                               mock_notify, mock_init, mock_from_frame):
        app = notifier.NotifierApplication()
        app.server = mock.Mock()

        app.recv_frame('test')

        mock_from_frame.assert_called_once_with('test')
        self.assertFalse(mock_notify.called)
        self.assertFalse(mock_disconnect.called)
        self.assertFalse(mock_closed.called)
        self.assertFalse(app.server.stop.called)
        app.server.notify.assert_called_once_with(mock_from_frame.return_value)

    @mock.patch.object(protocol, 'Message', return_value=mock.Mock(**{
        'to_frame.return_value': 'frame',
    }))
    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    @mock.patch.object(notifier.NotifierApplication, 'send_frame')
    @mock.patch.object(notifier.NotifierApplication, 'close')
    def test_disconnect_success(self, mock_close, mock_send_frame, mock_init,
                                mock_Message):
        app = notifier.NotifierApplication()

        app.disconnect()

        mock_Message.assert_called_once_with('goodbye')
        mock_Message.return_value.to_frame.assert_called_once_with()
        mock_send_frame.assert_called_once_with('frame')
        mock_close.assert_called_once_with()

    @mock.patch.object(protocol, 'Message', return_value=mock.Mock(**{
        'to_frame.return_value': 'frame',
    }))
    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    @mock.patch.object(notifier.NotifierApplication, 'send_frame',
                       side_effect=TestException('test'))
    @mock.patch.object(notifier.NotifierApplication, 'close')
    def test_disconnect_failure(self, mock_close, mock_send_frame, mock_init,
                                mock_Message):
        app = notifier.NotifierApplication()

        app.disconnect()

        mock_Message.assert_called_once_with('goodbye')
        mock_Message.return_value.to_frame.assert_called_once_with()
        mock_send_frame.assert_called_once_with('frame')
        mock_close.assert_called_once_with()

    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    @mock.patch.object(notifier.NotifierApplication, 'notify')
    def test_closed(self, mock_notify, mock_init):
        app = notifier.NotifierApplication()
        app.server = mock.Mock()

        app.closed(None)

        mock_notify.assert_called_once_with(
            'Connection Closed',
            'The connection to the HeyU hub has been closed.',
            notifier.DISCONNECTED)
        app.server.stop.assert_called_once_with()

    @mock.patch.object(protocol, 'Message', return_value='notification')
    @mock.patch.object(notifier.NotifierApplication, '__init__',
                       return_value=None)
    def test_notify(self, mock_init, mock_Message):
        app = notifier.NotifierApplication()
        app.server = mock.Mock()
        app.app_name = 'app_name'
        app.app_id = 'app_id'

        app.notify('summary', 'body', 'category')

        mock_Message.assert_called_once_with(
            'notify', summary='summary', body='body', category='category',
            app_name='app_name', id='app_id')
        app.server.notify.assert_called_once_with('notification')


class StdoutNotificationDriverTest(unittest.TestCase):
    @mock.patch.object(sys, 'stdout', io.BytesIO())
    @mock.patch.object(notifier, 'NotifierServer', return_value=[
        mock.Mock(id='notify-1', urgency=protocol.URGENCY_LOW,
                  app_name='application-1', summary='summary-1', body='body-1',
                  category='cat-1'),
        mock.Mock(id='notify-2', urgency=protocol.URGENCY_NORMAL,
                  app_name='application-2', summary='summary-2', body='body-2',
                  category=None),
        mock.Mock(id='notify-3', urgency=protocol.URGENCY_CRITICAL,
                  app_name='application-3', summary='summary-3', body='body-3',
                  category='cat-3'),
    ])
    def test_output(self, mock_NotifierServer):
        notifier.stdout_notification_driver('hub')

        mock_NotifierServer.assert_called_once_with('hub', None, True)
        self.assertEqual(
            'ID notify-1, urgency low\n'
            'Application: application-1\n'
            '    Summary: summary-1\n'
            '       Body: body-1\n'
            '   Category: cat-1\n'
            '\n'
            'ID notify-2, urgency normal\n'
            'Application: application-2\n'
            '    Summary: summary-2\n'
            '       Body: body-2\n'
            '   Category: None\n'
            '\n'
            'ID notify-3, urgency critical\n'
            'Application: application-3\n'
            '    Summary: summary-3\n'
            '       Body: body-3\n'
            '   Category: cat-3\n'
            '\n'
            'Notifications received: 3\n',
            sys.stdout.getvalue())


class MyBytesIO(io.BytesIO):
    """
    Override close() to preserve the emitted contents.
    """

    def close(self):
        self.contents = self.getvalue()
        super(MyBytesIO, self).close()


class FileNotificationDriverTest(unittest.TestCase):
    @mock.patch('__builtin__.open', return_value=MyBytesIO())
    @mock.patch.object(notifier, 'NotifierServer', return_value=[
        mock.Mock(id='notify-1', urgency=protocol.URGENCY_LOW,
                  app_name='application-1', summary='summary-1', body='body-1',
                  category='cat-1'),
        mock.Mock(id='notify-2', urgency=protocol.URGENCY_NORMAL,
                  app_name='application-2', summary='summary-2', body='body-2',
                  category=None),
        mock.Mock(id='notify-3', urgency=protocol.URGENCY_CRITICAL,
                  app_name='application-3', summary='summary-3', body='body-3',
                  category='cat-3'),
    ])
    def test_output(self, mock_NotifierServer, mock_open):
        notifier.file_notification_driver('file', 'hub')

        mock_open.assert_called_once_with('file', 'a')
        mock_NotifierServer.assert_called_once_with('hub', None, True)
        self.assertEqual(
            'ID notify-1, urgency low\n'
            'Application: application-1\n'
            '    Summary: summary-1\n'
            '       Body: body-1\n'
            '   Category: cat-1\n'
            'ID notify-2, urgency normal\n'
            'Application: application-2\n'
            '    Summary: summary-2\n'
            '       Body: body-2\n'
            '   Category: None\n'
            'ID notify-3, urgency critical\n'
            'Application: application-3\n'
            '    Summary: summary-3\n'
            '       Body: body-3\n'
            '   Category: cat-3\n',
            mock_open.return_value.contents)
