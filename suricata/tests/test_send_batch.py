import asyncio
import json
import os
import sys
import socket

import aiohttp
from aiohttp import web

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app import send_batch, settings


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    addr, port = s.getsockname()
    s.close()
    return port


async def test_send_batch():
    received = []

    async def handler(request):
        data = await request.json()
        received.append(data)
        return web.Response(text="ok")

    port = find_free_port()
    app = web.Application()
    app.router.add_post("/receive", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()

    settings.target_url = f"http://127.0.0.1:{port}/receive"

    async with aiohttp.ClientSession() as session:
        await send_batch(session, [{"a": 1}, {"b": 2}])

    # Wait a short time to ensure server processed request
    await asyncio.sleep(0.1)
    assert len(received) == 1
    assert isinstance(received[0], list)

    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(test_send_batch())
