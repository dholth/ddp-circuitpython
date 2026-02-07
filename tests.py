#!/usr/bin/env python

from ddp_receiver import *
import random


def test_header():
    for _ in range(256):
        flags1, device_id, offset, length = (
            random.randint(0, 0xFF),
            random.randint(0, 0xFF),
            random.randint(0, 0xFFFFFFFF),
            random.randint(0, 0xFFFF),
        )
        a = build_header(flags1, device_id, offset, length)
        b = build_header_2(flags1, device_id, offset, length)

        assert a == b
    print("Success")


if __name__ == "__main__":
    test_header()
