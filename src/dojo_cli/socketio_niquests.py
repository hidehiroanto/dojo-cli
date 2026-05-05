"""Niquests-backed Socket.IO transport helpers."""

import asyncio
from http.cookies import SimpleCookie
import inspect
from types import SimpleNamespace
from typing import Optional, cast

import engineio
import engineio.async_client as engineio_async_client
import engineio.base_client
import engineio.exceptions
import engineio.packet
from niquests import AsyncSession
from niquests.cookies import create_cookie
from niquests.exceptions import RequestException
from socketio import AsyncClient, AsyncSimpleClient

async def maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result

if engineio_async_client.aiohttp is None:
    engineio_async_client.aiohttp = SimpleNamespace(
        WSMsgType=SimpleNamespace(CLOSE='close', CLOSING='closing'),
        client_exceptions=SimpleNamespace(
            ClientConnectionError=OSError,
            ServerConnectionError=OSError,
            ServerDisconnectedError=OSError,
            WSServerHandshakeError=OSError
        )
    )

class ResponseAdapter:
    def __init__(self, response):
        self.response = response

    @property
    def status(self) -> int:
        return self.response.status_code

    async def close(self):
        await maybe_await(self.response.close())

    async def read(self) -> bytes:
        content = await maybe_await(self.response.content)
        return content or b''

class WebSocketAdapter:
    def __init__(self, response):
        self.response = response
        self.extension = response.extension
        if self.extension is None:
            raise RequestException('WebSocket upgrade failed')

    async def close(self):
        try:
            await maybe_await(self.extension.close())
        finally:
            await maybe_await(self.response.close())

    async def receive(self):
        try:
            data = await maybe_await(self.extension.next_payload())
        except RequestException as exc:
            raise OSError(exc) from exc

        if data is None:
            return SimpleNamespace(data=None, type='close')
        if isinstance(data, bytes):
            return SimpleNamespace(data=data, type='binary')
        return SimpleNamespace(data=data, type='text')

    async def send_bytes(self, data: bytes):
        try:
            await maybe_await(self.extension.send_payload(data))
        except RequestException as exc:
            raise OSError(exc) from exc

    async def send_str(self, data: str):
        try:
            await maybe_await(self.extension.send_payload(data))
        except RequestException as exc:
            raise OSError(exc) from exc

class SocketIoSession:
    def __init__(self, session_cookie: Optional[str] = None):
        self.closed = False
        self.session = AsyncSession()
        if session_cookie:
            self.session.cookies.set_cookie(create_cookie('session', session_cookie))

    @staticmethod
    def normalize_timeout(timeout):
        return timeout.total if hasattr(timeout, 'total') else timeout

    def update_cookies(self, cookies: dict[str, str]):
        for name, value in cookies.items():
            self.session.cookies.set_cookie(create_cookie(name, value))

    async def close(self):
        if not self.closed:
            await self.session.close()
            self.closed = True

    async def get(self, url: str, **kwargs) -> ResponseAdapter:
        return await self.request('GET', url, **kwargs)

    async def request(self, method: str, url: str, **kwargs) -> ResponseAdapter:
        timeout = self.normalize_timeout(kwargs.pop('timeout', None))
        response = await self.session.request(method, url, timeout=timeout, **kwargs)
        return ResponseAdapter(response)

    async def ws_connect(self, url: str, *, headers: Optional[dict] = None, timeout=None, verify: bool = True) -> WebSocketAdapter:
        return WebSocketAdapter(await self.session.get(url, headers=headers, stream=True, timeout=None, verify=verify))

class SocketIoEngineClient(engineio.AsyncClient):
    async def _connect_websocket(self, url, headers, engineio_path):
        websocket_url = self._get_engineio_url(url, engineio_path, 'websocket')
        if self.sid:
            self.logger.info('Attempting WebSocket upgrade to ' + websocket_url)
            upgrade = True
            websocket_url += '&sid=' + self.sid
        else:
            upgrade = False
            self.base_url = websocket_url
            self.logger.info('Attempting WebSocket connection to ' + websocket_url)

        if self.http is None or self.http.closed:
            self.http = SocketIoSession()

        headers = headers.copy()
        for header, value in list(headers.items()):
            if header.lower() == 'cookie':
                cookie_jar = SimpleCookie(value)
                self.http.update_cookies({key: morsel.value for key, morsel in cookie_jar.items()})
                del headers[header]
                break

        headers.update(self.websocket_extra_options.pop('headers', {}))

        try:
            timestamp_url = websocket_url + self._get_url_timestamp()
            ws = await self.http.ws_connect(timestamp_url, headers=headers, timeout=self.request_timeout, verify=self.ssl_verify)
        except RequestException:
            if upgrade:
                self.logger.warning('WebSocket upgrade failed: connection error')
                return False
            raise engineio.exceptions.ConnectionError('Connection error')

        if upgrade:
            packet_data = engineio.packet.Packet(engineio.packet.PING, data='probe').encode()
            try:
                await ws.send_str(packet_data)
                packet_data = (await ws.receive()).data
            except Exception as exc:
                self.logger.warning('WebSocket upgrade failed: unexpected exception: %s', str(exc))
                return False

            packet = engineio.packet.Packet(encoded_packet=packet_data)
            if packet.packet_type != engineio.packet.PONG or packet.data != 'probe':
                self.logger.warning('WebSocket upgrade failed: no PONG packet')
                return False

            packet_data = engineio.packet.Packet(engineio.packet.UPGRADE).encode()
            try:
                await ws.send_str(packet_data)
            except Exception as exc:
                self.logger.warning('WebSocket upgrade failed: unexpected send exception: %s', str(exc))
                return False

            self.current_transport = 'websocket'
            self.logger.info('WebSocket upgrade was successful')
        else:
            try:
                packet_data = (await ws.receive()).data
            except Exception as exc:
                raise engineio.exceptions.ConnectionError('Unexpected recv exception: ' + str(exc))

            open_packet = engineio.packet.Packet(encoded_packet=packet_data)
            if open_packet.packet_type != engineio.packet.OPEN:
                raise engineio.exceptions.ConnectionError('no OPEN packet')
            if not isinstance(open_packet.data, dict):
                raise engineio.exceptions.ConnectionError('invalid OPEN packet')

            packet_values = cast(dict[str, object], open_packet.data)

            self.logger.info('WebSocket connection accepted with ' + str(open_packet.data))
            self.sid = cast(str, packet_values['sid'])
            self.upgrades = cast(list[str], packet_values['upgrades'])
            self.ping_interval = int(cast(int | str, packet_values['pingInterval'])) / 1000.0
            self.ping_timeout = int(cast(int | str, packet_values['pingTimeout'])) / 1000.0
            self.current_transport = 'websocket'
            self.state = 'connected'
            engineio.base_client.connected_clients.append(self)
            await self._trigger_event('connect', run_async=False)

        self.ws = ws
        self.write_loop_task = self.start_background_task(self._write_loop)
        self.read_loop_task = self.start_background_task(self._read_loop_websocket)
        return True

    async def _send_request(self, method, url, headers=None, body=None, timeout=None):
        if self.http is None or self.http.closed:
            self.http = SocketIoSession()

        try:
            return await self.http.request(method, url, data=body, headers=headers, timeout=timeout, verify=self.ssl_verify)
        except RequestException as exc:
            self.logger.info('HTTP %s request to %s failed with error %s.', method, url, exc)
            return str(exc)

class SocketIoClient(AsyncClient):
    def _engineio_client_class(self):
        return SocketIoEngineClient

class SocketIoSimpleClient(AsyncSimpleClient):
    client_class = SocketIoClient

async def close_socketio_client(sio: Optional[SocketIoSimpleClient], http_session: Optional[SocketIoSession]):
    if sio is not None and sio.client is not None:
        engine_client = sio.client.eio
        engine_client.state = 'disconnected'
        tasks = [task for task in (engine_client.write_loop_task, engine_client.read_loop_task) if task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1)
            except asyncio.TimeoutError:
                pass
        if engine_client.ws is not None:
            try:
                await asyncio.wait_for(maybe_await(engine_client.ws.close()), timeout=1)
            except (asyncio.TimeoutError, OSError):
                pass
        sio.client = None
        sio.connected = False
        sio.connected_event.clear()

    if http_session is not None and not http_session.closed:
        try:
            await asyncio.wait_for(http_session.close(), timeout=1)
        except asyncio.TimeoutError:
            pass
