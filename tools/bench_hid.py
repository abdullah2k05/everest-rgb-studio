#!/usr/bin/env python3
"""Measure HID round-trip latency to tune exchange() timing.

    python tools/bench_hid.py [rounds]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from everest_rgb.hardware import detection, protocol  # noqa: E402
from everest_rgb.hardware.hid_device import HidTransport  # noqa: E402


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    info = detection.find_lighting_device()
    if info is None:
        print("device not found")
        return 1
    transport = HidTransport(info.path)
    transport.open()
    packet = protocol.build_set_mode(protocol.EFFECT_STATIC)

    try:
        for delay in (0.0, 0.005, 0.01, 0.02, 0.04):
            ok = 0
            start = time.perf_counter()
            for _ in range(rounds):
                transport.send_feature_report(packet, 0x16)
                if delay:
                    time.sleep(delay)
                resp = transport.read_feature_report()
                if len(resp) >= 2 and resp[1] == 0x16:
                    ok += 1
            elapsed = time.perf_counter() - start
            print(
                f"delay={delay*1000:5.1f}ms  {ok}/{rounds} echoes  "
                f"{elapsed/rounds*1000:6.1f} ms/packet"
            )
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
