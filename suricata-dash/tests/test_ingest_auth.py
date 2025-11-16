import asyncio
import base64
import os
import sys
import socket

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from aiohttp import web
import aiohttp

from cli import dashboard_state, settings, ingest_handler


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    _, port = s.getsockname()
    s.close()
    return port


async def test_ingest_basic_auth():
    port = find_free_port()
    settings.port = port
    settings.auth_type = "basic"
    settings.auth_username = "user"
    settings.auth_password = "pass"

    app = web.Application()
    app.router.add_post("/ingest", ingest_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', port)
    await site.start()

    async with aiohttp.ClientSession() as session:
        payload = [{"timestamp": "2025-01-01T00:00:00Z", "event_type": "alert"}]
        token = base64.b64encode(b"user:pass").decode()
        headers = {"Authorization": f"Basic {token}"}
        async with session.post(f"http://127.0.0.1:{port}/ingest", json=payload, headers=headers) as resp:
            assert resp.status == 200

    await asyncio.sleep(0.1)
    assert dashboard_state.total_received >= 1

    await runner.cleanup()


async def test_ingest_bearer_auth():
    port = find_free_port()
    settings.port = port
    settings.auth_type = "bearer"
    settings.auth_bearer_token = "s3cr3t"

    app = web.Application()
    app.router.add_post("/ingest", ingest_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', port)
    await site.start()

    async with aiohttp.ClientSession() as session:
        payload = [{"timestamp": "2025-01-01T00:00:00Z", "event_type": "alert"}]
        headers = {"Authorization": f"Bearer s3cr3t"}
        async with session.post(f"http://127.0.0.1:{port}/ingest", json=payload, headers=headers) as resp:
            assert resp.status == 200

    await asyncio.sleep(0.1)
    assert dashboard_state.total_received >= 1

    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(test_ingest_basic_auth())
    asyncio.run(test_ingest_bearer_auth())
