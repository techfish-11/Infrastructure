import asyncio
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


async def test_ingest_post():
    port = find_free_port()
    settings.port = port
    app = web.Application()
    app.router.add_post("/ingest", lambda request: request._message)
    # Instead of using existing handler, we start the server and post to it
    # Start the real dash server
    server_app = web.Application()
    server_app.router.add_post("/ingest", lambda request: request._message)

    # But we need to use the same code used by the CLI; we can't easily import the private handler
    # So we will directly test posting to the CLI server started separately
    app = web.Application()
    app.router.add_post("/ingest", ingest_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', port)
    await site.start()

    async with aiohttp.ClientSession() as session:
        payload = [{"timestamp": "2025-01-01T00:00:00Z", "event_type": "alert", "src_ip": "10.0.0.1", "dest_ip": "10.0.0.2", "alert": {"signature":"test sig"}}]
        async with session.post(f"http://127.0.0.1:{port}/ingest", json=payload) as resp:
            assert resp.status == 200

    # Wait a moment for the handler to process
    await asyncio.sleep(0.1)
    assert dashboard_state.total_received >= 1
    assert dashboard_state.event_type_counts.get("alert", 0) >= 1

    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(test_ingest_post())
