"""DDP receiver web server example with a live LED grid view."""

from __future__ import annotations

import http.server
import json
import queue
import socket
import socketserver
import threading
import time

from ddp_receiver import DDP_ID_DISPLAY, DDP_PORT, DDPReceiver

PIXEL_COUNT = 30
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 8000
MAX_BUFFER_SIZE = 2048

_state_lock = threading.Lock()
_state_colors: list[str] = ["#000000"] * PIXEL_COUNT


def _colors_from_buffer(data: bytearray) -> list[str]:
    colors: list[str] = []
    limit = min(len(data), PIXEL_COUNT * 3)
    for idx in range(0, limit, 3):
        r = data[idx]
        g = data[idx + 1]
        b = data[idx + 2]
        colors.append(f"#{r:02x}{g:02x}{b:02x}")
    while len(colors) < PIXEL_COUNT:
        colors.append("#000000")
    return colors


class SSEClient:
    def __init__(self) -> None:
        self.queue: queue.Queue[str] = queue.Queue()

    def send(self, message: str) -> None:
        self.queue.put(message)


class SSEHub:
    def __init__(self) -> None:
        self._clients: list[SSEClient] = []
        self._lock = threading.Lock()

    def add(self, client: SSEClient) -> None:
        with self._lock:
            self._clients.append(client)

    def remove(self, client: SSEClient) -> None:
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def broadcast(self, message: str) -> None:
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            client.send(message)


_hub = SSEHub()


def _get_state_json() -> str:
    with _state_lock:
        colors = list(_state_colors)
    return json.dumps({"colors": colors})


def _update_state_from_buffer(buffer: bytearray) -> None:
    colors = _colors_from_buffer(buffer)
    with _state_lock:
        _state_colors[:] = colors
    _hub.broadcast(json.dumps({"colors": colors}))


class DDPRequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "DDPWeb/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._handle_index()
            return
        if self.path == "/events":
            self._handle_events()
            return
        self.send_error(404)

    def _handle_index(self) -> None:
        html = _index_html(PIXEL_COUNT)
        encoded = html.encode("ascii")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=ascii")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(encoded)

    def _handle_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        # Don't try to handle another request after this one; 'Connection:
        # keep-alive' doesn't work for SSE.
        self.close_connection = True

        client = SSEClient()
        _hub.add(client)
        try:
            self._send_event(_get_state_json())
            while True:
                try:
                    message = client.queue.get(timeout=15.0)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                self._send_event(message)
        except (ConnectionError, BrokenPipeError):
            return
        finally:
            _hub.remove(client)

    def _send_event(self, payload: str) -> None:
        data = f"data: {payload}\n\n".encode("ascii")
        self.wfile.write(data)
        self.wfile.flush()


def _index_html(pixel_count: int) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="ascii">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DDP LED Grid</title>
  <style>
    :root {{
      --bg: #0f1013;
      --grid-bg: #15171c;
      --cell: 20px;
      --gap: 6px;
    }}
    html, body {{
      height: 100%;
      margin: 0;
      background: var(--bg);
      color: #e5e7eb;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .wrap {{
      display: grid;
      place-items: center;
      height: 100%;
      padding: 16px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(10, var(--cell));
      gap: var(--gap);
      padding: 16px;
      background: var(--grid-bg);
      border-radius: 12px;
      box-shadow: 0 12px 30px rgba(0,0,0,0.45);
    }}
    .cell {{
      width: var(--cell);
      height: var(--cell);
      border-radius: 4px;
      background: #000;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08);
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="grid" id="grid"></div>
  </div>
  <script>
    const count = {pixel_count};
    const grid = document.getElementById("grid");
    for (let i = 0; i < count; i++) {{
      const cell = document.createElement("div");
      cell.className = "cell";
      grid.appendChild(cell);
    }}
    const cells = Array.from(grid.children);
    const events = new EventSource("/events");
    events.onmessage = (ev) => {{
      const data = JSON.parse(ev.data);
      const colors = data.colors || [];
      for (let i = 0; i < cells.length; i++) {{
        cells[i].style.background = colors[i] || "#000000";
      }}
    }};
  </script>
</body>
</html>
"""


def _start_ddp_listener() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", DDP_PORT))
    receiver = DDPReceiver(sock, max_buffer_size=MAX_BUFFER_SIZE)

    def on_frame(device_id: int, buffer: bytearray, timecode: int | None) -> None:
        if device_id != DDP_ID_DISPLAY:
            return
        _update_state_from_buffer(buffer)

    receiver.configure_output(DDP_ID_DISPLAY, size=PIXEL_COUNT * 3, callback=on_frame)
    while True:
        receiver.poll()
        time.sleep(0.002)


def main() -> None:
    ddp_thread = threading.Thread(target=_start_ddp_listener, daemon=True)
    ddp_thread.start()

    print(
        f"Serving HTTP on {HTTP_HOST} port {HTTP_PORT} "
        f"(http://{HTTP_HOST}:{HTTP_PORT}/) ..."
    )

    with socketserver.ThreadingTCPServer(
        (HTTP_HOST, HTTP_PORT), DDPRequestHandler
    ) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
