"""Small DDP test sender for the web grid demo."""

from __future__ import annotations

import random
import socket
import time

from ddp_receiver import (
    DDP_FLAGS1_PUSH,
    DDP_FLAGS1_VER1,
    DDP_ID_DISPLAY,
    DDP_PORT,
    ddp_build_header,
)

PIXEL_COUNT = 30
DEST_HOST = "127.0.0.1"
DEST_PORT = DDP_PORT
FRAME_DELAY = 0.5


def _random_frame() -> bytes:
    data = bytearray(PIXEL_COUNT * 3)
    for idx in range(0, len(data)):
        data[idx] = random.randint(0, 255)
    return bytes(data)


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest = (DEST_HOST, DEST_PORT)
    try:
        while True:
            payload = _random_frame()
            header = ddp_build_header(
                DDP_FLAGS1_VER1 | DDP_FLAGS1_PUSH,
                DDP_ID_DISPLAY,
                0,
                len(payload),
            )
            sock.sendto(header + payload, dest)
            time.sleep(FRAME_DELAY)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
