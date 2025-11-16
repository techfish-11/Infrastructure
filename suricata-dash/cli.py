#!/usr/bin/env python
"""
Suricata Dashboard CLI

This tool receives forwarded Suricata events at an /ingest HTTP endpoint and displays a live SOC-style
dashboard in the terminal using Rich.
"""
import asyncio
import base64
import os
import argparse
import json
from collections import Counter, deque
from typing import Any, Dict, Deque, List, Optional

import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.align import Align
from rich.text import Text

load_dotenv()


class Settings:
    host: str = os.getenv("LISTEN_HOST", "0.0.0.0")
    port: int = int(os.getenv("LISTEN_PORT", "9000"))
    max_events: int = int(os.getenv("MAX_EVENTS", "1000"))
    auth_type: str = os.getenv("DASH_AUTH_TYPE", "none").lower()  # none/basic/bearer
    auth_username: str = os.getenv("DASH_AUTH_USERNAME", "")
    auth_password: str = os.getenv("DASH_AUTH_PASSWORD", "")
    auth_bearer_token: str = os.getenv("DASH_AUTH_BEARER_TOKEN", "")
    refresh: float = float(os.getenv("REFRESH_INTERVAL", "1.0"))


settings = Settings()

console = Console()


class DashboardState:
    def __init__(self, maxlen: int = 1000):
        self.events: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self.total_received: int = 0
        self.event_type_counts: Counter = Counter()
        self.src_ip_counts: Counter = Counter()
        self.dest_ip_counts: Counter = Counter()
        self.alert_counts: Counter = Counter()

    def clear(self):
        """Reset the dashboard state for testing or re-use."""
        self.events.clear()
        self.total_received = 0
        self.event_type_counts = Counter()
        self.src_ip_counts = Counter()
        self.dest_ip_counts = Counter()
        self.alert_counts = Counter()

    def ingest(self, event: Dict[str, Any]):
        self.events.appendleft(event)
        self.total_received += 1
        e_type = event.get("event_type", "unknown")
        self.event_type_counts[e_type] += 1
        src = event.get("src_ip") or event.get("src_ipv6")
        dst = event.get("dest_ip") or event.get("dest_ipv6")
        if src:
            self.src_ip_counts[src] += 1
        if dst:
            self.dest_ip_counts[dst] += 1
        alert = event.get("alert")
        if alert:
            sig = alert.get("signature") or str(alert.get("gid"))
            if sig:
                self.alert_counts[sig] += 1


dashboard_state = DashboardState(maxlen=settings.max_events)


def verify_auth(request: web.Request) -> bool:
    if settings.auth_type == "none":
        return True
    if settings.auth_type == "bearer":
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        token = header.split(" ", 1)[1]
        return token == settings.auth_bearer_token
    if settings.auth_type == "basic":
        header = request.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        token_b64 = header.split(" ", 1)[1]
        try:
            token = base64.b64decode(token_b64.encode()).decode()
        except Exception:
            return False
        try:
            user, pwd = token.split(":", 1)
            return user == settings.auth_username and pwd == settings.auth_password
        except Exception:
            return False
    return False


async def ingest_handler(request: web.Request) -> web.Response:
    # Authentication
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")
    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")
    events: List[Dict[str, Any]] = []
    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, dict):
        events = [payload]
    else:
        return web.Response(status=400, text="JSON must be object or array")
    for ev in events:
        dashboard_state.ingest(ev)
    return web.Response(status=200, text="OK")


async def health_handler(request: web.Request) -> web.Response:
    return web.Response(status=200, text="OK")


async def stats_handler(request: web.Request) -> web.Response:
    data = {
        "total_received": dashboard_state.total_received,
        "event_type_counts": dict(dashboard_state.event_type_counts),
        "top_src_ips": dashboard_state.src_ip_counts.most_common(10),
        "top_dest_ips": dashboard_state.dest_ip_counts.most_common(10),
        "top_alerts": dashboard_state.alert_counts.most_common(10),
    }
    return web.json_response(data)


def build_dashboard() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
    )
    layout["body"].split_row(Layout(name="left"), Layout(name="right"))

    # Header
    header_text = Text(" Suricata Dashboard ", style="bold white on blue")
    header_text.append(f"   Total Received: {dashboard_state.total_received}", style="bold white")
    layout["header"].update(Panel(Align.center(header_text)))

    # Left: Summary and top counters
    left_layout = Layout()
    left_layout.split_column(Layout(name="summary", size=6), Layout(name="top_src", ratio=1))

    summary_table = Table.grid(expand=True)
    summary_table.add_column(justify="left")
    summary_table.add_column(justify="right")
    summary_table.add_row("Total events", str(dashboard_state.total_received))
    summary_table.add_row("Event types", ", ".join(f"{k}:{v}" for k, v in dashboard_state.event_type_counts.items()))
    left_layout["summary"].update(Panel(summary_table, title="Summary"))

    # Top source IPs
    src_table = Table(title="Top Source IPs", show_header=True, header_style="bold magenta")
    src_table.add_column("IP")
    src_table.add_column("Count", justify="right")
    for ip, cnt in dashboard_state.src_ip_counts.most_common(10):
        src_table.add_row(ip, str(cnt))
    left_layout["top_src"].update(src_table)
    layout["left"].update(left_layout)

    # Right: Top Alerts and Recent Events
    right_layout = Layout()
    right_layout.split_column(Layout(name="alerts", size=8), Layout(name="recent", ratio=1))

    alert_table = Table(title="Top Alerts", show_header=True, header_style="bold yellow")
    alert_table.add_column("Signature")
    alert_table.add_column("Count", justify="right")
    for sig, cnt in dashboard_state.alert_counts.most_common(10):
        alert_table.add_row(str(sig), str(cnt))
    right_layout["alerts"].update(alert_table)

    recent_table = Table(title="Recent Events", show_header=True, header_style="bold green")
    recent_table.add_column("Time", style="dim", width=20)
    recent_table.add_column("Type")
    recent_table.add_column("Src")
    recent_table.add_column("Dst")
    recent_table.add_column("Info")
    # Recent events: use up to 10
    for ev in list(dashboard_state.events)[:10]:
        ts = ev.get("timestamp") or "-"
        et = ev.get("event_type", "-")
        src = ev.get("src_ip") or ev.get("src_ipv6") or "-"
        dst = ev.get("dest_ip") or ev.get("dest_ipv6") or "-"
        info = ""
        if ev.get("alert"):
            info = ev["alert"].get("signature", ev["alert"].get("gid", ""))
        recent_table.add_row(ts, et, src, dst, str(info))
    right_layout["recent"].update(recent_table)
    layout["right"].update(right_layout)

    return layout


async def start_web_server(app: web.Application, host: str, port: int):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    console.log(f"Listening for events at http://{host}:{port}/ingest")


async def dashboard_loop():
    app = web.Application()
    app.router.add_post("/ingest", ingest_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/stats", stats_handler)
    await start_web_server(app, settings.host, settings.port)

    with Live(build_dashboard(), refresh_per_second=1, screen=True) as live:
        while True:
            live.update(build_dashboard())
            await asyncio.sleep(settings.refresh)


async def dashboard_local_loop():
    """Start a dashboard display locally without a running web server.

    This is used when replaying events from a local eve.json file.
    """
    with Live(build_dashboard(), refresh_per_second=1, screen=True) as live:
        try:
            while True:
                live.update(build_dashboard())
                await asyncio.sleep(settings.refresh)
        except KeyboardInterrupt:
            return


def ingest_events_from_file(path: str) -> int:
    """Read a local eve.json file and ingest events into dashboard_state.

    Returns the number of events ingested.
    Supports both a JSON array or newline-delimited JSON (jsonlines).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Events file not found: {path}")
    ingested = 0
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    # Try to parse as a JSON array
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            events = [data]
        elif isinstance(data, list):
            events = data
        else:
            events = []
    except Exception:
        # Fallback: JSON Lines
        events = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                # Ignore invalid lines
                continue
    for ev in events:
        dashboard_state.ingest(ev)
        ingested += 1
    return ingested


def main():
    parser = argparse.ArgumentParser(description="Suricata Dashboard CLI")
    parser.add_argument("--local", nargs="?", const="eve.json", help="Read a local eve.json file and display it in the dashboard (default: ./eve.json)")
    args = parser.parse_args()
    try:
        if args.local:
            # Read events from file then display dashboard
            path = args.local
            console.log(f"Reading local events from {path}")
            try:
                ingested = ingest_events_from_file(path)
                console.log(f"Ingested {ingested} events from {path}")
            except FileNotFoundError as e:
                console.print(str(e))
                return
            try:
                asyncio.run(dashboard_local_loop())
            except KeyboardInterrupt:
                console.print("Exiting...")
        else:
            asyncio.run(dashboard_loop())
    except KeyboardInterrupt:
        console.print("Exiting...")


if __name__ == "__main__":
    main()
