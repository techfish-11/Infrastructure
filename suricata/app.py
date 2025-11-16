import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiofiles
import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel


load_dotenv()


@dataclass
class Settings:
    eve_file_path: str = os.getenv("EVE_FILE_PATH", "/var/log/suricata/eve.json")
    target_url: str = os.getenv("TARGET_URL", "")
    auth_type: str = os.getenv("HTTP_AUTH_TYPE", "none").lower()  # none/basic/bearer
    auth_username: str = os.getenv("HTTP_AUTH_USERNAME", "")
    auth_password: str = os.getenv("HTTP_AUTH_PASSWORD", "")
    auth_bearer_token: str = os.getenv("HTTP_AUTH_BEARER_TOKEN", "")
    batch_size: int = int(os.getenv("BATCH_SIZE", "50"))
    batch_interval: float = float(os.getenv("BATCH_INTERVAL", "2.0"))
    read_interval: float = float(os.getenv("READ_INTERVAL", "0.1"))
    log_level: str = os.getenv("LOG_LEVEL", "info")


settings = Settings()


class Stats(BaseModel):
    total_forwarded: int = 0
    last_forwarded_at: Optional[float] = None
    buffered: int = 0
    last_error: Optional[str] = None


app = FastAPI(title="Suricata EVE Forwarder")
stats = Stats()


def get_auth_headers() -> Dict[str, str]:
    if settings.auth_type == "basic":
        # Basic auth header requires base64 encoding; aiohttp supports BasicAuth
        return {}
    if settings.auth_type == "bearer":
        return {"Authorization": f"Bearer {settings.auth_bearer_token}"}
    return {}


async def send_batch(session: aiohttp.ClientSession, batch: List[Dict[str, Any]]):
    if not settings.target_url:
        stats.last_error = "TARGET_URL not configured"
        return
    headers = {"Content-Type": "application/json"}
    headers.update(get_auth_headers())
    try:
        if settings.auth_type == "basic":
            auth = aiohttp.BasicAuth(settings.auth_username, settings.auth_password)
            async with session.post(settings.target_url, json=batch, headers=headers, auth=auth) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    stats.last_error = f"HTTP {resp.status}: {text}"
                else:
                    stats.total_forwarded += len(batch)
                    stats.last_forwarded_at = time.time()
        else:
            async with session.post(settings.target_url, json=batch, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    stats.last_error = f"HTTP {resp.status}: {text}"
                else:
                    stats.total_forwarded += len(batch)
                    stats.last_forwarded_at = time.time()
    except Exception as e:
        stats.last_error = str(e)


async def tail_eve_file():
    buffer: List[Dict[str, Any]] = []
    last_send_time = time.time()
    file_path = settings.eve_file_path
    # Ensure file exists before trying to open it repeatedly
    while True:
        try:
            async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
                # Seek to end (start tailing) to only process new lines
                await f.seek(0, 2)
                while True:
                    line = await f.readline()
                    if not line:
                        # no new data
                        # if buffer is due to send because of interval
                        now = time.time()
                        if buffer and (len(buffer) >= settings.batch_size or (now - last_send_time) >= settings.batch_interval):
                            async with aiohttp.ClientSession() as session:
                                await send_batch(session, buffer.copy())
                            buffer.clear()
                            last_send_time = time.time()
                        await asyncio.sleep(settings.read_interval)
                        # handle file rotation (if file truncated)
                        try:
                            st = await aiofiles.os.stat(file_path)
                            if st.st_size < await f.tell():
                                # file was rotated/truncated
                                break
                        except Exception:
                            # if stat fails, break to reopen
                            break
                        continue
                    # Parse JSON line
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        buffer.append(obj)
                        stats.buffered = len(buffer)
                    except json.JSONDecodeError as e:
                        stats.last_error = f"JSON parse error: {e}"
                        # skip invalid JSON lines
                        continue
                    # If batch limit reached, send
                    if len(buffer) >= settings.batch_size:
                        async with aiohttp.ClientSession() as session:
                            await send_batch(session, buffer.copy())
                        buffer.clear()
                        last_send_time = time.time()
                        stats.buffered = 0
        except FileNotFoundError:
            # Wait for file to exist
            await asyncio.sleep(1.0)
            continue
        except Exception as e:
            stats.last_error = str(e)
            await asyncio.sleep(1.0)
            continue


@app.on_event("startup")
async def startup_event():
    # Start background tailing task
    asyncio.create_task(tail_eve_file())


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.get("/stats")
async def get_stats():
    return JSONResponse(stats.dict())


@app.post("/send_now")
async def send_now():
    # Manual trigger: read a chunk of the file and send it
    # This is a helper; it will just read the file from start and send latest lines - not efficient but ok for demo
    if not settings.target_url:
        raise HTTPException(status_code=400, detail="TARGET_URL is not configured")
    events: List[Dict[str, Any]] = []
    try:
        async with aiofiles.open(settings.eve_file_path, mode="r", encoding="utf-8") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                events.append(obj)
                if len(events) >= settings.batch_size:
                    break
        async with aiohttp.ClientSession() as session:
            await send_batch(session, events)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {settings.eve_file_path}")
    return JSONResponse({"sent": len(events)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), log_level=settings.log_level)
