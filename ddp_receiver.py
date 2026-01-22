"""DDP receiver for CircuitPython.

Listen on UDP port 4048, parse DDP packets, and update output buffers.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import socket
    from collections.abc import Callable

    PacketCallback = Callable[[int, bytearray, int | None], None]

import errno

# DDP constants
DDP_PORT = 4048

DDP_HEADER_LEN = 10
DDP_HEADER_LEN_TIME = 14

DDP_FLAGS1_VER = 0xC0
DDP_FLAGS1_VER1 = 0x40
DDP_FLAGS1_PUSH = 0x01
DDP_FLAGS1_QUERY = 0x02
DDP_FLAGS1_REPLY = 0x04
DDP_FLAGS1_STORAGE = 0x08
DDP_FLAGS1_TIME = 0x10

DDP_ID_DISPLAY = 1
DDP_ID_STATUS = 251
DDP_ID_CONFIG = 250
DDP_ID_ALL = 255


def build_header(flags1: int, device_id: int, offset: int, length: int) -> bytes:
    header = bytearray(DDP_HEADER_LEN)
    header[0] = flags1 & 0xFF
    header[1] = 0
    header[2] = 0
    header[3] = device_id & 0xFF
    header[4] = (offset >> 24) & 0xFF
    header[5] = (offset >> 16) & 0xFF
    header[6] = (offset >> 8) & 0xFF
    header[7] = offset & 0xFF
    header[8] = (length >> 8) & 0xFF
    header[9] = length & 0xFF
    return bytes(header)


def _parse_header(
    packet: bytes,
) -> tuple[int, int, int, int, int, int | None] | None:
    if len(packet) < DDP_HEADER_LEN:
        return None
    flags1 = packet[0]
    version = (flags1 & DDP_FLAGS1_VER) >> 6
    if version != 1:
        return None
    device_id = packet[3]
    offset = (packet[4] << 24) | (packet[5] << 16) | (packet[6] << 8) | packet[7]
    length = (packet[8] << 8) | packet[9]
    timecode = None
    if flags1 & DDP_FLAGS1_TIME:
        if len(packet) < DDP_HEADER_LEN_TIME:
            return None
        timecode = int.from_bytes(packet[10:14], "big")
    header_len = DDP_HEADER_LEN_TIME if (flags1 & DDP_FLAGS1_TIME) else DDP_HEADER_LEN
    return flags1, device_id, offset, length, header_len, timecode


class DDPReceiver:
    def __init__(
        self,
        sock: socket.socket,
        *,
        max_buffer_size: int = 4096,
        status_json: bytes | None = None,
    ) -> None:
        """
        status_json suggested schema:
            {"status":
            {
            "man"    : "device-manufacturer-string",
            "mod"    : "device-model-string",
            "ver"    : "device-version-string",
            "mac"    : "xx:xx:xx:xx:xx:xx:xx",
            "push"   : true,      (if PUSH supported)
            "ntp"    : true       (if NTP supported)
            }
            }
        """
        self._sock = sock
        self._max_buffer_size = max_buffer_size
        self._buffers: dict[int, bytearray] = {}
        self._callbacks: dict[int, PacketCallback] = {}
        self._status_json = status_json
        self._rx_buffer = bytearray(2048)
        try:
            self._sock.settimeout(0)
        except OSError:
            pass

    def configure_output(
        self,
        device_id: int,
        size: int,
        callback: PacketCallback | None = None,
    ) -> None:
        self._buffers[device_id] = bytearray(size)
        if callback is not None:
            self._callbacks[device_id] = callback

    def set_status(self, status_json: bytes) -> None:
        self._status_json = status_json

    def poll(self) -> int:
        processed = 0
        while True:
            try:
                nbytes, addr = self._sock.recvfrom_into(self._rx_buffer)
            except OSError as exc:
                if exc.args and exc.args[0] in (errno.EAGAIN,):
                    break
                raise
            if not nbytes:
                break
            packet_view = memoryview(self._rx_buffer)[:nbytes]
            self._process_packet(packet_view, addr)
            processed += 1
        return processed

    def _process_packet(self, packet: bytes | memoryview, addr) -> None:
        parsed = _parse_header(packet)
        if parsed is None:
            return
        flags1, device_id, offset, length, header_len, timecode = parsed

        if flags1 & DDP_FLAGS1_REPLY:
            return

        if flags1 & DDP_FLAGS1_QUERY:
            self._handle_query(device_id, addr)
            return

        if flags1 & DDP_FLAGS1_STORAGE:
            return

        # packet is normally memoryview for slice without copy
        data = packet[header_len : header_len + length]
        if device_id == DDP_ID_ALL:
            for target_id in list(self._buffers.keys()):
                self._write_to_buffer(target_id, offset, data)
                if flags1 & DDP_FLAGS1_PUSH:
                    self._handle_push(target_id, timecode)
            return

        self._write_to_buffer(device_id, offset, data)
        if flags1 & DDP_FLAGS1_PUSH:
            self._handle_push(device_id, timecode)

    def _write_to_buffer(self, device_id: int, offset: int, data: bytes) -> None:
        if device_id not in self._buffers:
            if offset + len(data) > self._max_buffer_size:
                return
            self._buffers[device_id] = bytearray(offset + len(data))

        buf = self._buffers[device_id]
        end = offset + len(data)
        if end > len(buf):
            if end > self._max_buffer_size:
                return
            buf.extend(b"\x00" * (end - len(buf)))
        buf[offset:end] = data

    def _handle_push(self, device_id: int, timecode: int | None) -> None:
        callback = self._callbacks.get(device_id)
        if callback is None:
            return
        callback(device_id, self._buffers[device_id], timecode)

    def _handle_query(self, device_id: int, addr) -> None:
        if device_id != DDP_ID_STATUS:
            self._send_empty_reply(device_id, addr)
            return
        if self._status_json is None:
            self._send_empty_reply(device_id, addr)
            return
        flags1 = DDP_FLAGS1_VER1 | DDP_FLAGS1_REPLY | DDP_FLAGS1_PUSH
        header = build_header(flags1, device_id, 0, len(self._status_json))
        self._sock.sendto(header + self._status_json, addr)

    def _send_empty_reply(self, device_id: int, addr) -> None:
        flags1 = DDP_FLAGS1_VER1 | DDP_FLAGS1_REPLY | DDP_FLAGS1_PUSH
        header = build_header(flags1, device_id, 0, 0)
        self._sock.sendto(header, addr)
