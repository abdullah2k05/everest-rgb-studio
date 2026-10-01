# Everest 60 HID protocol reference

All values below were verified against real hardware
(`3282:0005 MOUNTAIN EVEREST 360`) unless marked otherwise.

## Transport

- HID **feature reports**, size **65 bytes**, report ID `0x00`
- Correct interface: **0**, usage page `0x01`, usage `0x06` (keyboard
  collection). Interface 1 (`0x01/0x02`, mouse/system control) must not be
  used; it does not accept the lighting protocol.
- Path is found per enumeration (`hid.enumerate`), never hard-coded:
  hidraw numbering changes across replugs.

### Packet header

| Offset | Value |
|---|---|
| `[0]` | `0x00` report ID |
| `[1]` | command |
| `[2..4]` | magic `46 23 EA` |
| `[5..]` | command payload |

Every packet is validated (`protocol.validate_packet`) before it is written:
size, report ID, magic, command byte, and payload ranges (RGB 0-255,
brightness/speed quantized, LED index 0-255).

### Round trip

The keyboard echoes the command byte at `response[1]`.

```python
dev.send_feature_report(packet)          # 65 bytes
resp = dev.get_feature_report(0x00, 65)  # resp[1] == packet[1]
```

Measured latency with `python-hidapi` 0.14: **~0.4 ms per round trip**
(20/20 echoes with zero artificial delay). Under sustained full-map streaming
(~1900 packets/s) occasional transient `read error`s occur; these are retried
with backoff and never treated as a disconnect.

## Commands

### `0x16` SetMode (activate an effect)

```
[1]=0x16  [2..4]=magic  [5]=0x01  [9]=effect code
```

### `0x17` ModeDetails (colors / speed / brightness)

```
[1]=0x17  [2..4]=magic  [5]=effect
[7]=speed × 25   (0/25/50/75/100)
[8]=brightness × 25
[9]=color mode   0x00 single · 0x02 rainbow · 0x10 dual
[10]=direction
[12..14]=color1 RGB      [15..17]=color2 RGB
```

Colors are omitted when color mode is rainbow.

### `0x1A` Commit (latch)

```
[1]=0x1A  [2..4]=magic  [5]=effect code
```

Sent after mode changes and after every custom color map. Without it a freshly
written map may not latch.

## Firmware effect codes

| Code | Effect |
|---|---|
| `0x01` | Static |
| `0x02` | Wave |
| `0x03` | Tornado |
| `0x04` | Breathing |
| `0x05` | Reactive |
| `0x06` | Matrix |
| `0x07` | Custom (per-key) |
| `0x08` | Yeti |
| `0x09` | Off |

Direction values: `0x00` L→R, `0x02` T→B, `0x04` R→L, `0x06` B→T,
`0x0A` clockwise, `0x09` counter-clockwise.

## Per-key RGB (custom mode)

Sequence:

1. `0x16` SetMode with effect `0x07` — **without** `0x17` (a stray `0x17`
   flashes a default color over the map)
2. `0x1A` Commit
3. `0x34` Begin: `[5]=brightness×25`, `[6]=0xC0`
4. `0x35` Map packets (14 entries each)
5. `0x36` End
6. `0x1A` Commit (latches the map)

### Map entries

Each `0x35` packet carries 14 entries of 4 bytes starting at offset 9:

```
[led_index] [R] [G] [B]
```

- `[5]` = stream control: `0x0E` more, `0x0A` last
- 65 - 9 header bytes = 56 bytes = 14 × 4 entries
- **Index comes first.** Verified on hardware: entry `00 FF 00 00` lights
  LED 0 (ESC) red.

### Padding rule

108 LEDs (64 keys + 44 side) don't divide by 14; the final packet is padded by
**duplicating the last real entry**. Zero padding would be interpreted as
`index 0, black` and blank ESC.

## LED index map

Logical key order (row-major, matches `hardware/led_map.py`):

```
Row 0:   0 22 23 24 25 26 27 28 29 30 31 32 33 34
Row 1:  42 43 44 45 46 47 48 49 50 51 52 53 54 55
Row 2:  63 64 65 66 67 68 69 70 71 72 73 74 76
Row 3:  84 85 86 87 88 89 90 91 92 93 94 97 99 56
Row 4: 105 106 107 110 113 115 119 120 121
```

Side ring: `126..169` (44 LEDs), clockwise starting above ESC.

## Verified facts (do not re-derive)

```
VID 0x3282  PID 0x0005
keyboard HID: interface 0, usage 0x01/0x06
mouse HID:    interface 1, usage 0x01/0x02
python-hidapi works; send_feature_report() works
65-byte feature reports; command 0x16 echoes in response byte 1
static RGB control, per-key maps, firmware effects, side ring all confirmed
full 64-key map + headers: 10 packets, ~5 ms wall time
```
