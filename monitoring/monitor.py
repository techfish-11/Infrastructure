from typing import Any, Optional
import csv
from datetime import datetime
def record_result_csv(name: str, t: str, ok: bool, status: Any, resp_ms: Optional[float]) -> None:
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    csv_path = os.path.join(log_dir, "monitor_results.csv")
    now = datetime.now().isoformat()
    with open(csv_path, "a", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([now, name, t, ok, status, resp_ms if resp_ms is not None else ""])

import asyncio
import subprocess
import os
import time
import logging
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Tuple, Optional
from aiohttp import ClientSession
from prometheus_client import start_http_server, Gauge
import requests
import yaml

# --- 設定ゾーン（config.yamlから読み込み）

def load_config() -> dict:
    # 環境変数MONITOR_CONFIG_PATH優先、なければスクリプトと同じディレクトリのconfig.yaml
    config_path = os.environ.get("MONITOR_CONFIG_PATH")
    if not config_path:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.isfile(config_path):
        logger.error(f"設定ファイルが見つかりません: {config_path}")
        raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    logger.info(f"設定ファイル読み込み: {config_path}")
    return cfg


def setup_logging():
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "monitor.log")
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s')
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])

setup_logging()
logger = logging.getLogger("monitor")

config = load_config()
CHECK_INTERVAL = config.get("CHECK_INTERVAL", 15)
DISCORD_WEBHOOK_URL = config.get("DISCORD_WEBHOOK_URL")
MONITORED = config.get("MONITORED", [])

# --- Prometheus metrics
g_up = Gauge('svc_up', '0=down,1=up', ['name', 'type'])
g_response_ms = Gauge('svc_resp_ms', 'response time ms', ['name'])

# --- 内部状態：簡易デデュープ（障害重複防止）
last_state = {}  # name -> {"up": True/False, "since": timestamp}


from abc import ABC, abstractmethod

class Notifier(ABC):
    @abstractmethod
    async def notify(self, msg: str) -> None:
        pass

class DiscordNotifier(Notifier):
    def __init__(self, webhook_url: Optional[str]):
        self.webhook_url = webhook_url

    async def notify(self, msg: str) -> None:
        if not self.webhook_url:
            logger.warning("Discord webhook URL not set. Skipping notification.")
            return
        url = self.webhook_url
        data = {"content": msg}
        try:
            requests.post(url, json=data, timeout=10)
            logger.info(f"Sent Discord notification: {msg}")
        except Exception as e:
            logger.error(f"Discord send failed: {e}")

notifiers: List[Notifier] = [DiscordNotifier(DISCORD_WEBHOOK_URL)]

async def send_notification(msg: str) -> None:
    for notifier in notifiers:
        await notifier.notify(msg)

async def check_http(session: ClientSession, name: str, url: str, retries: int = 2, backoff: float = 2.0) -> Tuple[bool, Optional[float], Any]:
    attempt = 0
    while attempt <= retries:
        start = time.time()
        try:
            async with session.get(url, timeout=10) as r:
                ok = (200 <= r.status < 400)
                resp_ms = (time.time()-start)*1000
                return ok, resp_ms, r.status
        except Exception as e:
            logger.warning(f"HTTP check failed for {name} ({url}) (attempt {attempt+1}/{retries+1}): {e}")
            if attempt < retries:
                await asyncio.sleep(backoff * (2 ** attempt))
            attempt += 1
    return False, None, f"HTTP check failed after {retries+1} attempts"

async def check_tcp(host: str, port: int, retries: int = 2, backoff: float = 2.0) -> Tuple[bool, Any]:
    attempt = 0
    while attempt <= retries:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return True, 0
        except Exception as e:
            logger.warning(f"TCP check failed for {host}:{port} (attempt {attempt+1}/{retries+1}): {e}")
            if attempt < retries:
                await asyncio.sleep(backoff * (2 ** attempt))
            attempt += 1
    return False, f"TCP check failed after {retries+1} attempts"

def check_ping(host: str) -> bool:
    try:
        # platform-dependent; Linuxでの例
        proc = subprocess.run(["ping", "-c", "2", "-W", "2", host], capture_output=True)
        return proc.returncode == 0
    except Exception as e:
        logger.exception(f"Ping check failed for {host}: {e}")
        return False

def check_systemd(unit_name: str) -> bool:
    try:
        proc = subprocess.run(["systemctl", "is-active", "--quiet", unit_name])
        return proc.returncode == 0
    except Exception as e:
        logger.exception(f"systemd check failed for {unit_name}: {e}")
        return False

async def attempt_autorecover(entry: dict) -> None:
    t = entry['type']
    name = entry['name']
    try:
        if t == "systemd":
            svc = entry['target']
            logger.warning(f"Attempting restart of {svc}")
            subprocess.run(["sudo", "systemctl", "restart", svc])
            await asyncio.sleep(3)
        elif t == "docker":
            container = entry['target']
            logger.warning(f"Attempting restart of docker container {container}")
            subprocess.run(["sudo", "docker", "restart", container])
            await asyncio.sleep(3)
    except Exception as e:
        logger.exception(f"Autorecover failed for {name} ({t}): {e}")


class MonitorAgent:
    def __init__(self, monitored: List[dict]):
        self.monitored = monitored
        self.last_state: Dict[str, dict] = {}

    async def check_once(self, session: ClientSession) -> None:
        tasks = []
        for entry in self.monitored:
            t = entry['type']
            name = entry['name']
            if t == "http":
                tasks.append((name, asyncio.create_task(check_http(session, name, entry['target'], retries=2, backoff=2.0))))
            elif t == "tcp":
                host, port = entry['target']
                tasks.append((name, asyncio.create_task(check_tcp(host, port, retries=2, backoff=2.0))))
            elif t == "ping":
                ok = check_ping(entry['target'])
                fut = asyncio.get_event_loop().create_future()
                fut.set_result((ok, None))
                tasks.append((name, fut))
            elif t == "systemd":
                ok = check_systemd(entry['target'])
                fut = asyncio.get_event_loop().create_future()
                fut.set_result((ok, None))
                tasks.append((name, fut))
            else:
                fut = asyncio.get_event_loop().create_future()
                fut.set_result((False, f"unknown type {t}"))
                tasks.append((name, fut))
        # collect
        for name, task in tasks:
            try:
                res = await task
            except Exception as e:
                res = (False, str(e))
            # normalize
            if isinstance(res, tuple) and len(res) == 3:
                ok, resp_ms, status = res
            elif isinstance(res, tuple) and len(res) == 2:
                ok, info = res
                resp_ms = None
                status = info
            else:
                ok = False
                resp_ms = None
                status = str(res)
            # update metrics
            entry = next((e for e in self.monitored if e['name']==name), None)
            g_up.labels(name=name, type=entry['type']).set(1 if ok else 0)
            if resp_ms:
                g_response_ms.labels(name=name).set(resp_ms)
            # record result
            record_result_csv(name, entry['type'], ok, status, resp_ms)
            # state change logic
            prev = self.last_state.get(name, {"up": True})
            if ok and not prev.get("up", True):
                # recovered
                self.last_state[name] = {"up": True, "since": time.time()}
                msg = f"✅ RECOVERED: {name} ({entry['type']}) status={status}"
                logger.info(msg)
                await send_notification(msg)
            elif not ok and prev.get("up", True):
                # new down
                self.last_state[name] = {"up": False, "since": time.time()}
                msg = f"🚨 DOWN: {name} ({entry['type']}) status={status}"
                logger.error(msg)
                await send_notification(msg)
                await attempt_autorecover(entry)
            else:
                # stable state, nothing to do
                pass

async def main_loop():
    agent = MonitorAgent(MONITORED)
    async with ClientSession() as session:
        while True:
            try:
                await agent.check_once(session)
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt: graceful shutdown.")
                break
            except Exception as e:
                logger.exception(f"check error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        # start a Prometheus /metrics on port 9101
        start_http_server(9101)
        logger.info("metrics server listening on :9101")
        asyncio.run(main_loop())
    except FileNotFoundError as e:
        logger.critical(f"設定ファイルエラー: {e}")
        exit(2)
    except Exception as e:
        logger.critical(f"致命的エラー: {e}")
        exit(1)
