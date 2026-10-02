"""
Base High-Frequency WebSocket Client with Active Heartbeat,
RTT Latency Telemetry, and Zombie Connection Reaper.
"""
import asyncio
import time
import logging
from typing import Optional, Callable, Awaitable
import websockets

logger = logging.getLogger("IngestionBase")

class BaseWebSocketClient:
    def __init__(
        self,
        name: str,
        url: str,
        heartbeat_interval: float = 20.0,
        read_timeout: float = 10.0,
        reconnect_delay: float = 2.0,
    ):
        self.name = name
        self.url = url
        self.heartbeat_interval = heartbeat_interval
        self.read_timeout = read_timeout
        self.reconnect_delay = reconnect_delay

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running: bool = False
        self.is_connected: bool = False
        self.rtt_ms: float = 0.0
        self.last_msg_time: float = time.time()
        self.last_ping_time: float = 0.0
        self.message_count: int = 0

    async def start(self):
        self.is_running = True
        asyncio.create_task(self._lifecycle_loop())

    async def stop(self):
        self.is_running = False
        self.is_connected = False
        if self.ws:
            await self.ws.close()

    async def _lifecycle_loop(self):
        """Continuously maintains connection, handling failures and reconnections."""
        while self.is_running:
            try:
                logger.info(f"[{self.name}] Connecting to {self.url}...")
                async with websockets.connect(
                    self.url,
                    ping_interval=None,  # We manage application & protocol ping explicitly
                    ping_timeout=None,
                    max_size=10 * 1024 * 1024,
                    close_timeout=5,
                ) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.last_msg_time = time.time()
                    logger.info(f"[{self.name}] Connected successfully.")

                    # Run subscribe hook
                    await self.on_connect()

                    # Spawn concurrent tasks: receiver & heartbeat monitor
                    recv_task = asyncio.create_task(self._recv_loop())
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                    done, pending = await asyncio.wait(
                        [recv_task, heartbeat_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending:
                        task.cancel()

            except Exception as e:
                logger.warning(f"[{self.name}] Connection error: {e}. Reconnecting in {self.reconnect_delay}s...")
            finally:
                self.is_connected = False
                self.ws = None
                await self.on_disconnect()
                await asyncio.sleep(self.reconnect_delay)

    async def _recv_loop(self):
        """Receives incoming frames with read-deadline monitoring to reap zombie sockets."""
        while self.is_running and self.ws:
            try:
                # Enforce read deadline
                raw_msg = await asyncio.wait_for(self.ws.recv(), timeout=self.heartbeat_interval + self.read_timeout)
                self.last_msg_time = time.time()
                self.message_count += 1
                await self.on_message(raw_msg)
            except asyncio.TimeoutError:
                logger.error(f"[{self.name}] Zombie connection detected: Read timeout exceeded. Killing socket.")
                break
            except Exception as e:
                logger.warning(f"[{self.name}] Recv loop terminated: {e}")
                break

    async def _heartbeat_loop(self):
        """Sends periodic ping frames and measures Round-Trip Time (RTT)."""
        while self.is_running and self.ws:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                t0 = time.time()
                self.last_ping_time = t0
                await self.send_ping()
                # If pong handler completes, rtt is calculated
            except Exception as e:
                logger.warning(f"[{self.name}] Heartbeat failed: {e}")
                break

    async def send_ping(self):
        """Default protocol-level ping."""
        if self.ws:
            pong_waiter = await self.ws.ping()
            # Await pong with read timeout
            await asyncio.wait_for(pong_waiter, timeout=self.read_timeout)
            self.rtt_ms = round((time.time() - self.last_ping_time) * 1000, 2)

    async def on_connect(self):
        """Subclass hook when connection is established."""
        pass

    async def on_disconnect(self):
        """Subclass hook on disconnect."""
        pass

    async def on_message(self, message: str):
        """Subclass hook on new incoming WebSocket message."""
        pass

    def get_telemetry(self) -> dict:
        return {
            "name": self.name,
            "connected": self.is_connected,
            "rtt_ms": self.rtt_ms,
            "message_count": self.message_count,
            "last_msg_age_sec": round(time.time() - self.last_msg_time, 2),
        }
