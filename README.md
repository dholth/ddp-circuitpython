DDP CircuitPython
=================

A client for the [DDP Distributed Display Protocol](http://www.3waylabs.com/ddp/) for
CircuitPython, and testing utilities.

The Distributed Display Protocol is a way to send data to lighting displays.
This library was written to send colors from a device running the latest version
of the [WLED software](https://kno.wled.ge/) to a device that can only run
CircuitPython. The receiving device behaves like an additional LED strip
attached to the sending device.

## Installation

- `ddp_receiver.py` goes on the device. It requires Adafruit's
  [`neopixel.py`](https://github.com/adafruit/Adafruit_CircuitPython_NeoPixel/)
- `typing.py` just defines `TYPE_CHECKING=False` in case CircuitPython doesn't
  have the typing module.
- `sketch.py` should be uploaded as `code.py` on the device. It demonstrates
  connecting the reciever to a 30-LED strip.


## Testing

- `ddp_web_server.py` runs on your computer. It simulates a LED strip in the web
  browser. It listens on http://localhost:8000/
- `ddp_sender_demo.py` also runs on your computer. It sends colors to
  `ddp_web_server.py`, and the browser displays them in real time. It can be
  edited to send colors to a real device.

## Credits

Written by Daniel Holth <dholth@gmail.com>, AI assisted.

MIT license.