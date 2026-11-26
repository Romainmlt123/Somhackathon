"""Client autonome du village. Les décisions ne bloquent jamais la lecture réseau."""

import asyncio
import json
import uuid
from collections import deque

from websockets.asyncio.client import connect


class Inbox:
    def __init__(self, limit=256):
        self.items = deque()
        self.wake = asyncio.Event()
        self.limit = limit

    def put(self, frame):
        if frame["type"] == "snapshot":
            self.items.clear()
        elif frame["type"] == "scan":
            self.items = deque(f for f in self.items if f["type"] != "scan")
        if len(self.items) >= self.limit:
            raise BufferError("Le lecteur de décisions doit reprendre un instantané.")
        self.items.append(frame)
        self.wake.set()

    async def get(self):
        while not self.items:
            self.wake.clear()
            await self.wake.wait()
        return self.items.popleft()


class Agent:
    def __init__(self, url, token, version, decide):
        self.url, self.token, self.version, self.decide = url, token, version, decide
        self.socket = None
        self.pending = {}

    async def send(self, kind, data, command_id=None):
        command_id = command_id or uuid.uuid4().hex
        frame = json.dumps(dict(type=kind, command_id=command_id, data=data))
        self.pending[command_id] = frame
        await self.socket.send(frame)
        return command_id

    async def run_once(self):
        async with connect(
            self.url,
            additional_headers={"Authorization": "Bearer " + self.token},
            max_size=2**20,
        ) as ws:
            self.socket = ws
            await ws.send(json.dumps({"type": "hello", "agent_version": self.version}))
            inbox = Inbox()

            async def reader():
                async for message in ws:
                    frame = json.loads(message)
                    if frame["type"] == "command_result":
                        self.pending.pop(frame["data"]["command_id"], None)
                    inbox.put(frame)

            async def decisions():
                first = await inbox.get()
                for message in list(self.pending.values()):
                    await ws.send(message)
                await self.decide(first, self.send)
                while True:
                    await self.decide(await inbox.get(), self.send)

            tasks = [asyncio.create_task(reader()), asyncio.create_task(decisions())]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self.socket = None
