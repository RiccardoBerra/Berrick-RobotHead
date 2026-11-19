"""LED ring used for the "light-based gazing" social cue."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Protocol

from .config import LedConfig

log = logging.getLogger(__name__)

Color = Sequence[int]


class Pixels(Protocol):
    def set(self, i: int, color: Color) -> None: ...
    def show(self) -> None: ...
    def close(self) -> None: ...


class NeopixelSpi:
    """Adafruit neopixel_spi on SPI MOSI (GPIO10). Works on Pi 1-5."""

    def __init__(self, cfg: LedConfig) -> None:
        import board
        import neopixel_spi

        order = neopixel_spi.GRBW if cfg.rgbw else neopixel_spi.GRB
        self._px = neopixel_spi.NeoPixel_SPI(
            board.SPI(), cfg.count, pixel_order=order, brightness=cfg.brightness, auto_write=False
        )
        self._rgbw = cfg.rgbw

    def set(self, i: int, color: Color) -> None:
        self._px[i] = tuple(color[:4] if self._rgbw else color[:3])

    def show(self) -> None:
        self._px.show()

    def close(self) -> None:
        self._px.fill((0, 0, 0, 0) if self._rgbw else (0, 0, 0))
        self._px.show()
        self._px.deinit()


class RpiWs281x:
    """rpi_ws281x (the 2019 driver). Pi 1-4 only, needs root."""

    def __init__(self, cfg: LedConfig) -> None:
        from rpi_ws281x import PixelStrip, ws

        strip_type = ws.SK6812_STRIP_RGBW if cfg.rgbw else ws.WS2811_STRIP_GRB
        self._strip = PixelStrip(
            cfg.count, cfg.gpio_pin, 800_000, 10, False, int(255 * cfg.brightness), 0, strip_type
        )
        self._strip.begin()

    def set(self, i: int, color: Color) -> None:
        from rpi_ws281x import Color as C

        r, g, b, *rest = list(color) + [0]
        self._strip.setPixelColor(i, C(r, g, b, rest[0]))

    def show(self) -> None:
        self._strip.show()

    def close(self) -> None:
        from rpi_ws281x import Color as C

        for i in range(self._strip.numPixels()):
            self._strip.setPixelColor(i, C(0, 0, 0, 0))
        self._strip.show()


class MockPixels:
    def __init__(self, cfg: LedConfig) -> None:
        self.pixels: list[tuple[int, ...]] = [(0, 0, 0, 0)] * cfg.count

    def set(self, i: int, color: Color) -> None:
        self.pixels[i] = tuple(color)

    def show(self) -> None:
        log.debug("leds: %s", self.pixels[0])

    def close(self) -> None:
        pass


class LedRing:
    def __init__(self, cfg: LedConfig, pixels: Pixels | None = None) -> None:
        self._cfg = cfg
        if pixels is not None:
            self._px: Pixels | None = pixels
        elif cfg.backend == "none":
            self._px = None
        elif cfg.backend == "neopixel_spi":
            self._px = NeopixelSpi(cfg)
        elif cfg.backend == "rpi_ws281x":
            self._px = RpiWs281x(cfg)
        elif cfg.backend == "mock":
            self._px = MockPixels(cfg)
        else:
            raise ValueError(f"unknown led backend '{cfg.backend}'")

    def wipe(self, color: Color) -> None:
        """Light pixels one at a time, like the original colorWipe()."""
        if self._px is None:
            return
        delay = self._cfg.wipe_ms / 1000
        for i in range(self._cfg.count):
            self._px.set(i, color)
            if delay > 0:
                self._px.show()
                time.sleep(delay)
        self._px.show()

    def engaged(self) -> None:
        self.wipe(self._cfg.engaged_color)

    def idle(self) -> None:
        self.wipe(self._cfg.idle_color)

    def close(self) -> None:
        if self._px is not None:
            self._px.close()
