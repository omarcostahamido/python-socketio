import asyncio
import logging
import sys
import unittest
from unittest import mock

from engineio import json
import pytest

from socketio import asyncio_server
from socketio import asyncio_namespace
from socketio import exceptions
from socketio import namespace
from socketio import packet


def AsyncMock(*args, **kwargs):
    """Return a mock asynchronous function."""
    m = mock.MagicMock(*args, **kwargs)

    async def mock_coro(*args, **kwargs):
        return m(*args, **kwargs)

    mock_coro.mock = m
    return mock_coro


def _run(coro):
    """Run the given coroutine."""
    return asyncio.get_event_loop().run_until_complete(coro)


@unittest.skipIf(sys.version_info < (3, 5), 'only for Python 3.5+')
@mock.patch('socketio.server.engineio.AsyncServer', **{
    'return_value.generate_id.side_effect': [str(i) for i in range(1, 10)]})
class TestAsyncServer(unittest.TestCase):
    def tearDown(self):
        # restore JSON encoder, in case a test changed it
        packet.Packet.json = json

    def _get_mock_manager(self):
        mgr = mock.MagicMock()
        mgr.can_disconnect = AsyncMock()
        mgr.emit = AsyncMock()
        mgr.close_room = AsyncMock()
        mgr.trigger_callback = AsyncMock()
        return mgr

    def test_create(self, eio):
        eio.return_value.handle_request = AsyncMock()
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(
            client_manager=mgr, async_handlers=True, foo='bar'
        )
        _run(s.handle_request({}))
        _run(s.handle_request({}))
        eio.assert_called_once_with(**{'foo': 'bar', 'async_handlers': False})
        assert s.manager == mgr
        assert s.eio.on.call_count == 3
        assert s.async_handlers

    def test_attach(self, eio):
        s = asyncio_server.AsyncServer()
        s.attach('app', 'path')
        eio.return_value.attach.assert_called_once_with('app', 'path')

    def test_on_event(self, eio):
        s = asyncio_server.AsyncServer()

        @s.on('connect')
        def foo():
            pass

        def bar():
            pass

        s.on('disconnect', bar)
        s.on('disconnect', bar, namespace='/foo')

        assert s.handlers['/']['connect'] == foo
        assert s.handlers['/']['disconnect'] == bar
        assert s.handlers['/foo']['disconnect'] == bar

    def test_emit(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        _run(
            s.emit(
                'my event',
                {'foo': 'bar'},
                to='room',
                skip_sid='123',
                namespace='/foo',
                callback='cb',
            )
        )
        s.manager.emit.mock.assert_called_once_with(
            'my event',
            {'foo': 'bar'},
            '/foo',
            room='room',
            skip_sid='123',
            callback='cb',
        )
        _run(
            s.emit(
                'my event',
                {'foo': 'bar'},
                room='room',
                skip_sid='123',
                namespace='/foo',
                callback='cb',
            )
        )
        s.manager.emit.mock.assert_called_with(
            'my event',
            {'foo': 'bar'},
            '/foo',
            room='room',
            skip_sid='123',
            callback='cb',
        )

    def test_emit_default_namespace(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        _run(
            s.emit(
                'my event',
                {'foo': 'bar'},
                to='room',
                skip_sid='123',
                callback='cb',
            )
        )
        s.manager.emit.mock.assert_called_once_with(
            'my event',
            {'foo': 'bar'},
            '/',
            room='room',
            skip_sid='123',
            callback='cb',
        )
        _run(
            s.emit(
                'my event',
                {'foo': 'bar'},
                room='room',
                skip_sid='123',
                callback='cb',
            )
        )
        s.manager.emit.mock.assert_called_with(
            'my event',
            {'foo': 'bar'},
            '/',
            room='room',
            skip_sid='123',
            callback='cb',
        )

    def test_send(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        _run(
            s.send(
                'foo',
                to='room',
                skip_sid='123',
                namespace='/foo',
                callback='cb',
            )
        )
        s.manager.emit.mock.assert_called_once_with(
            'message',
            'foo',
            '/foo',
            room='room',
            skip_sid='123',
            callback='cb',
        )
        _run(
            s.send(
                'foo',
                room='room',
                skip_sid='123',
                namespace='/foo',
                callback='cb',
            )
        )
        s.manager.emit.mock.assert_called_with(
            'message',
            'foo',
            '/foo',
            room='room',
            skip_sid='123',
            callback='cb',
        )

    def test_call(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)

        async def fake_event_wait():
            s.manager.emit.mock.call_args_list[0][1]['callback']('foo', 321)
            return True

        s.eio.create_event.return_value.wait = fake_event_wait
        assert _run(s.call('foo', sid='123')) == ('foo', 321)

    def test_call_with_timeout(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)

        async def fake_event_wait():
            await asyncio.sleep(1)

        s.eio.create_event.return_value.wait = fake_event_wait
        with pytest.raises(exceptions.TimeoutError):
            _run(s.call('foo', sid='123', timeout=0.01))

    def test_call_with_broadcast(self, eio):
        s = asyncio_server.AsyncServer()
        with pytest.raises(ValueError):
            _run(s.call('foo'))

    def test_call_without_async_handlers(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(
            client_manager=mgr, async_handlers=False
        )
        with pytest.raises(RuntimeError):
            _run(s.call('foo', sid='123', timeout=12))

    def test_enter_room(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        s.enter_room('123', 'room', namespace='/foo')
        s.manager.enter_room.assert_called_once_with('123', '/foo', 'room')

    def test_enter_room_default_namespace(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        s.enter_room('123', 'room')
        s.manager.enter_room.assert_called_once_with('123', '/', 'room')

    def test_leave_room(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        s.leave_room('123', 'room', namespace='/foo')
        s.manager.leave_room.assert_called_once_with('123', '/foo', 'room')

    def test_leave_room_default_namespace(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        s.leave_room('123', 'room')
        s.manager.leave_room.assert_called_once_with('123', '/', 'room')

    def test_close_room(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        _run(s.close_room('room', namespace='/foo'))
        s.manager.close_room.mock.assert_called_once_with('room', '/foo')

    def test_close_room_default_namespace(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        _run(s.close_room('room'))
        s.manager.close_room.mock.assert_called_once_with('room', '/')

    def test_rooms(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        s.rooms('123', namespace='/foo')
        s.manager.get_rooms.assert_called_once_with('123', '/foo')

    def test_rooms_default_namespace(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        s.rooms('123')
        s.manager.get_rooms.assert_called_once_with('123', '/')

    def test_handle_request(self, eio):
        eio.return_value.handle_request = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s.handle_request('environ'))
        s.eio.handle_request.mock.assert_called_once_with('environ')

    def test_emit_internal(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._emit_internal('123', 'my event', 'my data', namespace='/foo'))
        s.eio.send.mock.assert_called_once_with(
            '123', '2/foo,["my event","my data"]'
        )

    def test_emit_internal_with_tuple(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(
            s._emit_internal(
                '123', 'my event', ('foo', 'bar'), namespace='/foo'
            )
        )
        s.eio.send.mock.assert_called_once_with(
            '123', '2/foo,["my event","foo","bar"]'
        )

    def test_emit_internal_with_list(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(
            s._emit_internal(
                '123', 'my event', ['foo', 'bar'], namespace='/foo'
            )
        )
        s.eio.send.mock.assert_called_once_with(
            '123', '2/foo,["my event",["foo","bar"]]'
        )

    def test_emit_internal_with_none(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._emit_internal('123', 'my event', None, namespace='/foo'))
        s.eio.send.mock.assert_called_once_with(
            '123', '2/foo,["my event"]'
        )

    def test_emit_internal_with_callback(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        id = s.manager._generate_ack_id('1', 'cb')
        _run(
            s._emit_internal(
                '123', 'my event', 'my data', namespace='/foo', id=id
            )
        )
        s.eio.send.mock.assert_called_once_with(
            '123', '2/foo,1["my event","my data"]'
        )

    def test_emit_internal_default_namespace(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._emit_internal('123', 'my event', 'my data'))
        s.eio.send.mock.assert_called_once_with(
            '123', '2["my event","my data"]'
        )

    def test_emit_internal_binary(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._emit_internal('123', u'my event', b'my binary data'))
        assert s.eio.send.mock.call_count == 2

    def test_transport(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        s.eio.transport = mock.MagicMock(return_value='polling')
        _run(s._handle_eio_connect('foo', 'environ'))
        assert s.transport('foo') == 'polling'
        s.eio.transport.assert_called_once_with('foo')

    def test_handle_connect(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        s.manager.initialize = mock.MagicMock()
        handler = mock.MagicMock()
        s.on('connect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        assert s.manager.is_connected('1', '/')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_called_once_with('123', '0{"sid":"1"}')
        assert s.manager.initialize.call_count == 1
        _run(s._handle_eio_connect('456', 'environ'))
        _run(s._handle_eio_message('456', '0'))
        assert s.manager.initialize.call_count == 1

    def test_handle_connect_with_auth(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        s.manager.initialize = mock.MagicMock()
        handler = mock.MagicMock()
        s.on('connect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0{"token":"abc"}'))
        assert s.manager.is_connected('1', '/')
        handler.assert_called_once_with('1', 'environ', {'token': 'abc'})
        s.eio.send.mock.assert_called_once_with('123', '0{"sid":"1"}')
        assert s.manager.initialize.call_count == 1
        _run(s._handle_eio_connect('456', 'environ'))
        _run(s._handle_eio_message('456', '0'))
        assert s.manager.initialize.call_count == 1

    def test_handle_connect_with_auth_none(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        s.manager.initialize = mock.MagicMock()
        handler = mock.MagicMock(side_effect=[TypeError, None, None])
        s.on('connect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        assert s.manager.is_connected('1', '/')
        handler.assert_called_with('1', 'environ', None)
        s.eio.send.mock.assert_called_once_with('123', '0{"sid":"1"}')
        assert s.manager.initialize.call_count == 1
        _run(s._handle_eio_connect('456', 'environ'))
        _run(s._handle_eio_message('456', '0'))
        assert s.manager.initialize.call_count == 1

    def test_handle_connect_async(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        s.manager.initialize = mock.MagicMock()
        handler = AsyncMock()
        s.on('connect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        assert s.manager.is_connected('1', '/')
        handler.mock.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_called_once_with('123', '0{"sid":"1"}')
        assert s.manager.initialize.call_count == 1
        _run(s._handle_eio_connect('456', 'environ'))
        _run(s._handle_eio_message('456', '0'))
        assert s.manager.initialize.call_count == 1

    def test_handle_connect_namespace(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        handler = mock.MagicMock()
        s.on('connect', handler, namespace='/foo')
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        assert s.manager.is_connected('1', '/foo')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_called_once_with('123', '0/foo,{"sid":"1"}')

    def test_handle_connect_always_connect(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(always_connect=True)
        s.manager.initialize = mock.MagicMock()
        handler = mock.MagicMock()
        s.on('connect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        assert s.manager.is_connected('1', '/')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_called_once_with('123', '0{"sid":"1"}')
        assert s.manager.initialize.call_count == 1
        _run(s._handle_eio_connect('456', 'environ'))
        _run(s._handle_eio_message('456', '0'))
        assert s.manager.initialize.call_count == 1

    def test_handle_connect_rejected(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        handler = mock.MagicMock(return_value=False)
        s.on('connect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        assert not s.manager.is_connected('1', '/foo')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_called_once_with(
            '123', '4{"message":"Connection rejected by server"}')
        assert s.environ == {'123': 'environ'}

    def test_handle_connect_namespace_rejected(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        handler = mock.MagicMock(return_value=False)
        s.on('connect', handler, namespace='/foo')
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        assert not s.manager.is_connected('1', '/foo')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_any_call(
            '123', '4/foo,{"message":"Connection rejected by server"}')
        assert s.environ == {'123': 'environ'}

    def test_handle_connect_rejected_always_connect(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(always_connect=True)
        handler = mock.MagicMock(return_value=False)
        s.on('connect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        assert not s.manager.is_connected('1', '/')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_any_call('123', '0{"sid":"1"}')
        s.eio.send.mock.assert_any_call(
            '123', '1{"message":"Connection rejected by server"}')
        assert s.environ == {'123': 'environ'}

    def test_handle_connect_namespace_rejected_always_connect(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(always_connect=True)
        handler = mock.MagicMock(return_value=False)
        s.on('connect', handler, namespace='/foo')
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        assert not s.manager.is_connected('1', '/foo')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_any_call('123', '0/foo,{"sid":"1"}')
        s.eio.send.mock.assert_any_call(
            '123', '1/foo,{"message":"Connection rejected by server"}')
        assert s.environ == {'123': 'environ'}

    def test_handle_connect_rejected_with_exception(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        handler = mock.MagicMock(
            side_effect=exceptions.ConnectionRefusedError('fail_reason')
        )
        s.on('connect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        assert not s.manager.is_connected('1', '/')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_called_once_with(
            '123', '4{"message":"fail_reason"}')
        assert s.environ == {'123': 'environ'}

    def test_handle_connect_rejected_with_empty_exception(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        handler = mock.MagicMock(
            side_effect=exceptions.ConnectionRefusedError()
        )
        s.on('connect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        assert not s.manager.is_connected('1', '/')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_called_once_with(
            '123', '4{"message":"Connection rejected by server"}')
        assert s.environ == {'123': 'environ'}

    def test_handle_connect_namespace_rejected_with_exception(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        handler = mock.MagicMock(
            side_effect=exceptions.ConnectionRefusedError(
                'fail_reason', 1, '2')
        )
        s.on('connect', handler, namespace='/foo')
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        assert not s.manager.is_connected('1', '/foo')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_called_once_with(
            '123', '4/foo,{"message":"fail_reason","data":[1,"2"]}')
        assert s.environ == {'123': 'environ'}

    def test_handle_connect_namespace_rejected_with_empty_exception(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        handler = mock.MagicMock(
            side_effect=exceptions.ConnectionRefusedError()
        )
        s.on('connect', handler, namespace='/foo')
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        assert not s.manager.is_connected('1', '/foo')
        handler.assert_called_once_with('1', 'environ')
        s.eio.send.mock.assert_called_once_with(
            '123', '4/foo,{"message":"Connection rejected by server"}')
        assert s.environ == {'123': 'environ'}

    def test_handle_disconnect(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        s.manager.disconnect = mock.MagicMock()
        handler = mock.MagicMock()
        s.on('disconnect', handler)
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        _run(s._handle_eio_disconnect('123'))
        handler.assert_called_once_with('1')
        s.manager.disconnect.assert_called_once_with('1', '/')
        assert s.environ == {}

    def test_handle_disconnect_namespace(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        handler = mock.MagicMock()
        s.on('disconnect', handler)
        handler_namespace = mock.MagicMock()
        s.on('disconnect', handler_namespace, namespace='/foo')
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        _run(s._handle_eio_disconnect('123'))
        handler.assert_not_called()
        handler_namespace.assert_called_once_with('1')
        assert s.environ == {}

    def test_handle_disconnect_only_namespace(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        handler = mock.MagicMock()
        s.on('disconnect', handler)
        handler_namespace = mock.MagicMock()
        s.on('disconnect', handler_namespace, namespace='/foo')
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        _run(s._handle_eio_message('123', '1/foo,'))
        assert handler.call_count == 0
        handler_namespace.assert_called_once_with('1')
        assert s.environ == {'123': 'environ'}

    def test_handle_disconnect_unknown_client(self, eio):
        mgr = self._get_mock_manager()
        s = asyncio_server.AsyncServer(client_manager=mgr)
        _run(s._handle_eio_disconnect('123'))

    def test_handle_event(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        sid = s.manager.connect('123', '/')
        handler = AsyncMock()
        catchall_handler = AsyncMock()
        s.on('msg', handler)
        s.on('*', catchall_handler)
        _run(s._handle_eio_message('123', '2["msg","a","b"]'))
        _run(s._handle_eio_message('123', '2["my message","a","b","c"]'))
        handler.mock.assert_called_once_with(sid, 'a', 'b')
        catchall_handler.mock.assert_called_once_with(
            'my message', sid, 'a', 'b', 'c')

    def test_handle_event_with_namespace(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        sid = s.manager.connect('123', '/foo')
        handler = mock.MagicMock()
        catchall_handler = mock.MagicMock()
        s.on('msg', handler, namespace='/foo')
        s.on('*', catchall_handler, namespace='/foo')
        _run(s._handle_eio_message('123', '2/foo,["msg","a","b"]'))
        _run(s._handle_eio_message('123', '2/foo,["my message","a","b","c"]'))
        handler.assert_called_once_with(sid, 'a', 'b')
        catchall_handler.assert_called_once_with(
            'my message', sid, 'a', 'b', 'c')

    def test_handle_event_with_disconnected_namespace(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        s.manager.connect('123', '/foo')
        handler = mock.MagicMock()
        s.on('my message', handler, namespace='/bar')
        _run(s._handle_eio_message('123', '2/bar,["my message","a","b","c"]'))
        handler.assert_not_called()

    def test_handle_event_binary(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        sid = s.manager.connect('123', '/')
        handler = mock.MagicMock()
        s.on('my message', handler)
        _run(
            s._handle_eio_message(
                '123',
                '52-["my message","a",'
                '{"_placeholder":true,"num":1},'
                '{"_placeholder":true,"num":0}]',
            )
        )
        _run(s._handle_eio_message('123', b'foo'))
        _run(s._handle_eio_message('123', b'bar'))
        handler.assert_called_once_with(sid, 'a', b'bar', b'foo')

    def test_handle_event_binary_ack(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        s.manager.trigger_callback = AsyncMock()
        sid = s.manager.connect('123', '/')
        _run(
            s._handle_eio_message(
                '123',
                '61-321["my message","a",' '{"_placeholder":true,"num":0}]',
            )
        )
        _run(s._handle_eio_message('123', b'foo'))
        s.manager.trigger_callback.mock.assert_called_once_with(
            sid, 321, ['my message', 'a', b'foo']
        )

    def test_handle_event_with_ack(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        sid = s.manager.connect('123', '/')
        handler = mock.MagicMock(return_value='foo')
        s.on('my message', handler)
        _run(s._handle_eio_message('123', '21000["my message","foo"]'))
        handler.assert_called_once_with(sid, 'foo')
        s.eio.send.mock.assert_called_once_with(
            '123', '31000["foo"]'
        )

    def test_handle_event_with_ack_none(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        sid = s.manager.connect('123', '/')
        handler = mock.MagicMock(return_value=None)
        s.on('my message', handler)
        _run(s._handle_eio_message('123', '21000["my message","foo"]'))
        handler.assert_called_once_with(sid, 'foo')
        s.eio.send.mock.assert_called_once_with('123', '31000[]')

    def test_handle_event_with_ack_tuple(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        sid = s.manager.connect('123', '/')
        handler = mock.MagicMock(return_value=(1, '2', True))
        s.on('my message', handler)
        _run(s._handle_eio_message('123', '21000["my message","a","b","c"]'))
        handler.assert_called_once_with(sid, 'a', 'b', 'c')
        s.eio.send.mock.assert_called_once_with(
            '123', '31000[1,"2",true]'
        )

    def test_handle_event_with_ack_list(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        sid = s.manager.connect('123', '/')
        handler = mock.MagicMock(return_value=[1, '2', True])
        s.on('my message', handler)
        _run(s._handle_eio_message('123', '21000["my message","a","b","c"]'))
        handler.assert_called_once_with(sid, 'a', 'b', 'c')
        s.eio.send.mock.assert_called_once_with(
            '123', '31000[[1,"2",true]]'
        )

    def test_handle_event_with_ack_binary(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer(async_handlers=False)
        sid = s.manager.connect('123', '/')
        handler = mock.MagicMock(return_value=b'foo')
        s.on('my message', handler)
        _run(s._handle_eio_message('123', '21000["my message","foo"]'))
        handler.assert_any_call(sid, 'foo')

    def test_handle_error_packet(self, eio):
        s = asyncio_server.AsyncServer()
        with pytest.raises(ValueError):
            _run(s._handle_eio_message('123', '4'))

    def test_handle_invalid_packet(self, eio):
        s = asyncio_server.AsyncServer()
        with pytest.raises(ValueError):
            _run(s._handle_eio_message('123', '9'))

    def test_send_with_ack(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        cb = mock.MagicMock()
        id1 = s.manager._generate_ack_id('1', cb)
        id2 = s.manager._generate_ack_id('1', cb)
        _run(s._emit_internal('123', 'my event', ['foo'], id=id1))
        _run(s._emit_internal('123', 'my event', ['bar'], id=id2))
        _run(s._handle_eio_message('123', '31["foo",2]'))
        cb.assert_called_once_with('foo', 2)

    def test_send_with_ack_namespace(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        cb = mock.MagicMock()
        id = s.manager._generate_ack_id('1', cb)
        _run(
            s._emit_internal(
                '123', 'my event', ['foo'], namespace='/foo', id=id
            )
        )
        _run(s._handle_eio_message('123', '3/foo,1["foo",2]'))
        cb.assert_called_once_with('foo', 2)

    def test_session(self, eio):
        fake_session = {}

        async def fake_get_session(eio_sid):
            assert eio_sid == '123'
            return fake_session

        async def fake_save_session(eio_sid, session):
            global fake_session
            assert eio_sid == '123'
            fake_session = session

        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        s.eio.get_session = fake_get_session
        s.eio.save_session = fake_save_session

        async def _test():
            await s._handle_eio_connect('123', 'environ')
            await s._handle_eio_message('123', '0')
            await s._handle_eio_message('123', '0/ns')
            sid = s.manager.sid_from_eio_sid('123', '/')
            sid2 = s.manager.sid_from_eio_sid('123', '/ns')
            await s.save_session(sid, {'foo': 'bar'})
            async with s.session(sid) as session:
                assert session == {'foo': 'bar'}
                session['foo'] = 'baz'
                session['bar'] = 'foo'
            assert await s.get_session(sid) == {'foo': 'baz', 'bar': 'foo'}
            assert fake_session == {'/': {'foo': 'baz', 'bar': 'foo'}}
            async with s.session(sid2, namespace='/ns') as session:
                assert session == {}
                session['a'] = 'b'
            assert await s.get_session(sid2, namespace='/ns') == {'a': 'b'}
            assert fake_session == {
                '/': {'foo': 'baz', 'bar': 'foo'},
                '/ns': {'a': 'b'},
            }

        _run(_test())

    def test_disconnect(self, eio):
        eio.return_value.send = AsyncMock()
        eio.return_value.disconnect = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        _run(s.disconnect('1'))
        s.eio.send.mock.assert_any_call('123', '1')
        assert not s.manager.is_connected('1', '/')

    def test_disconnect_ignore_queue(self, eio):
        eio.return_value.send = AsyncMock()
        eio.return_value.disconnect = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        _run(s.disconnect('1', ignore_queue=True))
        s.eio.send.mock.assert_any_call('123', '1')
        assert not s.manager.is_connected('1', '/')

    def test_disconnect_namespace(self, eio):
        eio.return_value.send = AsyncMock()
        eio.return_value.disconnect = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        _run(s.disconnect('1', namespace='/foo'))
        s.eio.send.mock.assert_any_call('123', '1/foo,')
        assert not s.manager.is_connected('1', '/foo')

    def test_disconnect_twice(self, eio):
        eio.return_value.send = AsyncMock()
        eio.return_value.disconnect = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0'))
        _run(s.disconnect('1'))
        calls = s.eio.send.mock.call_count
        assert not s.manager.is_connected('1', '/')
        _run(s.disconnect('1'))
        assert calls == s.eio.send.mock.call_count

    def test_disconnect_twice_namespace(self, eio):
        eio.return_value.send = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        _run(s.disconnect('1', namespace='/foo'))
        calls = s.eio.send.mock.call_count
        assert not s.manager.is_connected('1', '/foo')
        _run(s.disconnect('1', namespace='/foo'))
        assert calls == s.eio.send.mock.call_count

    def test_namespace_handler(self, eio):
        eio.return_value.send = AsyncMock()
        result = {}

        class MyNamespace(asyncio_namespace.AsyncNamespace):
            def on_connect(self, sid, environ):
                result['result'] = (sid, environ)

            async def on_disconnect(self, sid):
                result['result'] = ('disconnect', sid)

            async def on_foo(self, sid, data):
                result['result'] = (sid, data)

            def on_bar(self, sid):
                result['result'] = 'bar'

            async def on_baz(self, sid, data1, data2):
                result['result'] = (data1, data2)

        s = asyncio_server.AsyncServer(async_handlers=False)
        s.register_namespace(MyNamespace('/foo'))
        _run(s._handle_eio_connect('123', 'environ'))
        _run(s._handle_eio_message('123', '0/foo,'))
        assert result['result'] == ('1', 'environ')
        _run(s._handle_eio_message('123', '2/foo,["foo","a"]'))
        assert result['result'] == ('1', 'a')
        _run(s._handle_eio_message('123', '2/foo,["bar"]'))
        assert result['result'] == 'bar'
        _run(s._handle_eio_message('123', '2/foo,["baz","a","b"]'))
        assert result['result'] == ('a', 'b')
        _run(s.disconnect('1', '/foo'))
        assert result['result'] == ('disconnect', '1')

    def test_bad_namespace_handler(self, eio):
        class Dummy(object):
            pass

        class SyncNS(namespace.Namespace):
            pass

        s = asyncio_server.AsyncServer()
        with pytest.raises(ValueError):
            s.register_namespace(123)
        with pytest.raises(ValueError):
            s.register_namespace(Dummy)
        with pytest.raises(ValueError):
            s.register_namespace(Dummy())
        with pytest.raises(ValueError):
            s.register_namespace(namespace.Namespace)
        with pytest.raises(ValueError):
            s.register_namespace(SyncNS())

    def test_logger(self, eio):
        s = asyncio_server.AsyncServer(logger=False)
        assert s.logger.getEffectiveLevel() == logging.ERROR
        s.logger.setLevel(logging.NOTSET)
        s = asyncio_server.AsyncServer(logger=True)
        assert s.logger.getEffectiveLevel() == logging.INFO
        s.logger.setLevel(logging.WARNING)
        s = asyncio_server.AsyncServer(logger=True)
        assert s.logger.getEffectiveLevel() == logging.WARNING
        s.logger.setLevel(logging.NOTSET)
        s = asyncio_server.AsyncServer(logger='foo')
        assert s.logger == 'foo'

    def test_engineio_logger(self, eio):
        asyncio_server.AsyncServer(engineio_logger='foo')
        eio.assert_called_once_with(
            **{'logger': 'foo', 'async_handlers': False}
        )

    def test_custom_json(self, eio):
        # Warning: this test cannot run in parallel with other tests, as it
        # changes the JSON encoding/decoding functions

        class CustomJSON(object):
            @staticmethod
            def dumps(*args, **kwargs):
                return '*** encoded ***'

            @staticmethod
            def loads(*args, **kwargs):
                return '+++ decoded +++'

        asyncio_server.AsyncServer(json=CustomJSON)
        eio.assert_called_once_with(
            **{'json': CustomJSON, 'async_handlers': False}
        )

        pkt = packet.Packet(
            packet_type=packet.EVENT,
            data={'foo': 'bar'},
        )
        assert pkt.encode() == '2*** encoded ***'
        pkt2 = packet.Packet(encoded_packet=pkt.encode())
        assert pkt2.data == '+++ decoded +++'

        # restore the default JSON module
        packet.Packet.json = json

    def test_async_handlers(self, eio):
        s = asyncio_server.AsyncServer(async_handlers=True)
        s.manager.connect('123', '/')
        _run(s._handle_eio_message('123', '2["my message","a","b","c"]'))
        s.eio.start_background_task.assert_called_once_with(
            s._handle_event_internal,
            s,
            '1',
            '123',
            ['my message', 'a', 'b', 'c'],
            '/',
            None,
        )

    def test_start_background_task(self, eio):
        s = asyncio_server.AsyncServer()
        s.start_background_task('foo', 'bar', baz='baz')
        s.eio.start_background_task.assert_called_once_with(
            'foo', 'bar', baz='baz'
        )

    def test_sleep(self, eio):
        eio.return_value.sleep = AsyncMock()
        s = asyncio_server.AsyncServer()
        _run(s.sleep(1.23))
        s.eio.sleep.mock.assert_called_once_with(1.23)
