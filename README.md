# Everest RGB Studio

Linux RGB control for the **MOUNTAIN Everest 60** keyboard — a native,
open-source replacement for MOUNTAIN Base Camp.

Dark Qt interface, interactive per-key RGB painting, firmware effects, a
software effect engine, presets, side LED ring control, and direct HID
communication. Runs without root.

> Unofficial project, not affiliated with or endorsed by MOUNTAIN.

---

## Features

- **Automatic device detection** by VID/PID + HID usage (never hard-codes
  `/dev/hidraw*`, survives replugs)
- **Firmware effects**: Static, Wave, Tornado, Breathing, Reactive, Matrix,
  Yeti, Off — with color, secondary color, speed, brightness, direction
- **Per-key RGB**: click, ctrl-click, rubber-band, row and select-all; paint
  by dragging; undo/redo
- **Software effects** (rendered on the host, streamed to the keyboard):
  Static, Breathing, Rainbow, Wave, Gradient, Reactive, Fire, Ocean, Matrix
- **Side LED ring** (44 LEDs) with independent color control
- **Presets**: save / load / duplicate / import / export, plus 11 built-ins
- **Reconnection**: unplug/replug is handled automatically, the last lighting
  state is restored
- **CLI** for quick control and protocol debugging

## Supported hardware

| | |
|---|---|
| Device | MOUNTAIN Everest 60 (`MOUNTAIN EVEREST 360` in USB descriptors) |
| VID:PID | `3282:0005` (ANSI) / `3282:0006` (ISO) |
| Interface | 0 (keyboard collection, usage page `0x01`, usage `0x06`) |
| Protocol | 65-byte HID feature reports |
| Keys | 64 per-key RGB + 44 side ring LEDs |

Interface 1 (mouse/system control, usage `0x02`) is never used.

## Installation

Dependencies:

- Python ≥ 3.10
- `python-hidapi` (Arch: `pacman -S python-hidapi`)
- `PySide6` for the GUI (Arch: `pacman -S pyside6`)

### Run from source

```bash
git clone <this repo> everest-rgb-studio
cd everest-rgb-studio

python -m venv --system-site-packages .venv
.venv/bin/pip install -e .[gui]

.venv/bin/everest-rgb-gui          # GUI
.venv/bin/everest-rgb detect       # CLI
```

`--system-site-packages` lets the venv see the distro's `hid` module; if you
prefer, `pip install hidapi` inside the venv works too.

### Desktop entry (app launcher)

So the GUI shows up in your application launcher:

```bash
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
ln -sf /path/to/everest-rgb-studio/.venv/bin/everest-rgb-gui ~/.local/bin/
ln -sf /path/to/everest-rgb-studio/.venv/bin/everest-rgb     ~/.local/bin/
cp packaging/everest-rgb-studio.desktop ~/.local/share/applications/
cp packaging/icons/everest-rgb-studio.svg ~/.local/share/icons/hicolor/scalable/apps/
```

### Arch package

```bash
cd packaging
makepkg -si
```

## HID permissions

Normal users need read/write access to the keyboard's `hidraw` node. Install
the provided udev rule (no root-only workaround, never run the GUI with
`sudo`):

```bash
sudo cp packaging/99-everest-rgb-studio.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger
```

Then unplug and replug the keyboard. The rule grants the logged-in user
(`uaccess`) plus the `input` group access to `3282:0005` hidraw nodes.

## CLI

```bash
everest-rgb detect                      # list HID interfaces, show the pick
everest-rgb test                        # safe round-trip test (0x16/0x17/0x1A echo)
everest-rgb static --color "#ff0000"    # solid color
everest-rgb static --color "#0080ff" --brightness 75
everest-rgb effect wave --color1 "#0080ff" --color2 "#aa00ff" --speed 75
everest-rgb effect breathing --color1 "#ff4400"
everest-rgb color --keys W,A,S,D --color "#00a8ff"   # per-key paint
everest-rgb side --color "#ff00ff"       # side LED ring
everest-rgb brightness 60
everest-rgb off
everest-rgb preset list
everest-rgb preset load Ocean
everest-rgb gui
```

Add `--debug` to any command to log TX/RX packets.

## GUI

```bash
everest-rgb-gui
```

- **Lighting** — effect mode, colors, brightness/speed/direction, painting
- **Effects** — software effect designer (streams live to the keyboard)
- **Presets** — save/load/import/export
- **Settings** — reconnection, state persistence, frame rate, debug logging

Shortcuts: `Ctrl+Z` / `Ctrl+Shift+Z` undo/redo, `Ctrl+A` select all,
`Esc` clear selection, `Ctrl+B` toggle paint mode, `Ctrl+S` save preset,
`Ctrl+1..4` switch pages.

## Presets

User presets live in:

```text
~/.local/share/everest-rgb-studio/presets/*.json
```

Schema (versioned, evolvable):

```json
{
  "schema": 1,
  "name": "Coding",
  "mode": "custom",
  "effect": "static",
  "brightness": 80,
  "speed": 50,
  "color1": "#00A8FF",
  "color2": "#000000",
  "color_mode": 0,
  "direction": "left_to_right",
  "keys": { "W": "#00A8FF", "A": "#00A8FF", "S": "#00A8FF", "D": "#00A8FF" },
  "side": ["#101010"]
}
```

`mode` is one of `hardware` (firmware effect), `software` (host-rendered
effect) or `custom` (per-key map). Missing keys default to black.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `permission denied opening /dev/hidrawN` | Install the udev rule (above), replug |
| `Everest 60 not found` | Check `everest-rgb detect`; try another USB port/cable |
| Wrong keys light up | Run `everest-rgb test` first; report your model (ANSI/ISO) |
| GUI starts but stays disconnected | Check `~/.local/share/everest-rgb-studio/logs/everest-rgb.log` |
| Animation stutters | Lower frame rate in Settings (default 25 FPS) |

Debug logging (`--debug` or Settings → Debug logging) records full TX/RX
packet traces to the log file.

## Development

```bash
python -m venv --system-site-packages .venv
.venv/bin/pip install -e .[gui,dev]
.venv/bin/python -m pytest          # unit tests, no hardware needed
ruff check src tests tools          # lint
```

Architecture — the UI never builds raw HID packets:

```text
UI (PySide6)
  → AppController (central state, undo, presets)
    → HardwareService (worker thread, coalescing, reconnect)
      → Everest60 (high-level API)
        → protocol.py (validated 65-byte packet builders)
          → HidTransport (hidapi feature reports)
```

```
src/everest_rgb/
├── hardware/    detection, protocol, transport, controller, service
├── effects/     base types, software effects, engine thread
├── models/      keyboard layout, lighting state, presets
├── ui/          main window, keyboard widget, panels, theme
├── presets/     store + built-in preset JSON
└── utils/       logging, XDG configuration
```

Tools: `tools/gen_builtin_presets.py` regenerates built-ins,
`tools/bench_hid.py` measures round-trip latency.

## Protocol reference

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the reverse-engineered Everest 60
protocol: report layout, commands `0x16/0x17/0x1A/0x34/0x35/0x36`, the LED
index map, and measured timings.

## Credits

Protocol reverse-engineering builds on
[BaseCamp-Linux](https://github.com/) (reference implementation) and the
OpenRGB Mountain controller findings. This application is an independent
implementation.

## License

MIT — see [LICENSE](LICENSE).
