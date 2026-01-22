"""DDP receiver example for a 30-pixel RGB NeoPixel strip over WiFi."""

from __future__ import annotations

import board
import neopixel
import socketpool
import wifi

from ddp_receiver import DDP_ID_DISPLAY, DDP_PORT, DDPReceiver

PIXEL_COUNT = 30
PIXEL_PIN = board.D10
PIXEL_ORDER = neopixel.RGB
MAX_BUFFER_SIZE = 512


def _update_pixels(pixels: neopixel.NeoPixel, data: bytearray) -> None:
    pixel_bytes = min(len(data), PIXEL_COUNT * 3)
    for idx in range(0, pixel_bytes, 3):
        pixel = idx // 3
        pixels[pixel] = (data[idx], data[idx + 1], data[idx + 2])
    pixels.show()


def _make_status_json() -> bytes:
    return b'{"status":{"man":"circuitpython","mod":"ddp-receiver","ver":"1.0"}}'


def main() -> None:
    # wifi connects automatically using settings.toml,
    # also exposed through os.getenv(name)

    pool = socketpool.SocketPool(wifi.radio)
    sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
    sock.bind(("", DDP_PORT))

    pixels = neopixel.NeoPixel(
        PIXEL_PIN,
        PIXEL_COUNT,
        brightness=1.0,
        auto_write=False,
        pixel_order=PIXEL_ORDER,
    )

    def on_frame(device_id: int, buffer: bytearray, timecode: int | None) -> None:
        if device_id != DDP_ID_DISPLAY:
            return
        _update_pixels(pixels, buffer)

    receiver = DDPReceiver(
        sock,
        max_buffer_size=MAX_BUFFER_SIZE,
        status_json=_make_status_json(),
    )
    receiver.configure_output(DDP_ID_DISPLAY, size=PIXEL_COUNT * 3, callback=on_frame)

    while True:
        receiver.poll()


main()
