"""Effect engine tests - pure rendering, no hardware."""


from everest_rgb.effects.base import RenderContext, scale
from everest_rgb.effects.engine import EffectEngine, get_effect
from everest_rgb.effects.standard import EFFECT_CLASSES, EFFECTS
from everest_rgb.hardware.led_map import NUM_KEYS, NUM_SIDE_LEDS
from everest_rgb.models.lighting import LightingState


def _ctx(state: LightingState | None = None, t: float = 1.0) -> RenderContext:
    return RenderContext(state=state or LightingState(), t=t, dt=0.033)


def test_registry_contains_expected_effects():
    expected = {
        "static", "breathing", "rainbow", "wave", "gradient",
        "reactive", "fire", "ocean", "matrix",
    }
    assert expected == set(EFFECTS)


def test_every_effect_renders_full_frame():
    for cls in EFFECT_CLASSES:
        effect = cls()
        keys, side = effect.render(_ctx())
        assert len(keys) == NUM_KEYS, cls.name
        assert len(side) == NUM_SIDE_LEDS, cls.name
        for color in list(keys) + list(side):
            assert len(color) == 3
            assert all(0 <= c <= 255 for c in color), (cls.name, color)


def test_brightness_scales_output():
    effect = EFFECTS["static"]
    bright = LightingState()
    bright.brightness = 100
    bright.fill_keys((200, 100, 50))
    keys_bright, _ = effect.render(_ctx(bright))

    dim = bright.copy()
    dim.brightness = 50
    keys_dim, _ = effect.render(_ctx(dim))

    assert keys_bright[0] == (200, 100, 50)
    assert keys_dim[0] == (100, 50, 25)


def test_static_uses_painted_map():
    state = LightingState()
    state.fill_keys((10, 20, 30))
    keys, _ = EFFECTS["static"].render(_ctx(state))
    assert keys[0] == (10, 20, 30)


def test_gradient_interpolates_endpoints():
    state = LightingState()
    state.color1 = (0, 0, 0)
    state.color2 = (255, 255, 255)
    keys, _ = EFFECTS["gradient"].render(_ctx(state))
    # leftmost key darker than rightmost key
    assert sum(keys[0]) < sum(keys[13])


def test_breathing_varies_over_time():
    state = LightingState()
    state.fill_keys((255, 255, 255))
    effect = EFFECTS["breathing"]
    values = []
    for t in (0.0, 0.5, 1.0, 1.5, 2.0):
        keys, _ = effect.render(_ctx(state, t=t))
        values.append(keys[0][0])
    assert min(values) < max(values), "breathing must change brightness over time"


def test_reactive_lights_pressed_key():
    state = LightingState()
    state.fill_keys((0, 0, 0))
    state.color1 = (255, 0, 0)
    ctx = RenderContext(state=state, t=0.0, dt=0.01, pressed=(4,))  # key index 4
    keys, _ = EFFECTS["reactive"].render(ctx)
    assert keys[4] == (255, 0, 0)
    assert keys[5] != (255, 0, 0)


def test_engine_emits_initial_frame_then_quiet():
    """A static state must be sent once, not at every tick."""
    sent = []

    def on_frame(keys, side, brightness):
        sent.append((tuple(keys), tuple(side), brightness))

    engine = EffectEngine(on_frame, fps=30)
    state = LightingState()
    state.fill_keys((0, 128, 255))
    engine.set_state(state)
    engine.start()
    try:
        import time

        deadline = time.time() + 1.5
        while time.time() < deadline and len(sent) < 1:
            time.sleep(0.02)
        time.sleep(0.3)
    finally:
        engine.stop()
    assert len(sent) >= 1
    assert engine.frames_rendered >= 5
    # static content should not be re-pushed every rendered frame
    assert engine.frames_sent <= 2
    assert sent[0][2] == 100


def test_engine_animation_pushes_frames():
    sent = []

    def on_frame(keys, side, brightness):
        sent.append(keys)

    engine = EffectEngine(on_frame, fps=30)
    state = LightingState()
    state.mode = "software"
    state.effect = "rainbow"
    engine.set_state(state)
    engine.start()
    try:
        import time

        time.sleep(0.5)
    finally:
        engine.stop()
    assert len(sent) >= 3, "animated effect should push multiple frames"


def test_get_effect_unknown():
    assert get_effect("does-not-exist") is None
    assert get_effect("ocean") is not None


def test_scale_helper():
    assert scale((100, 200, 300), 0.5) == (50, 100, 150)
    assert scale((10, 10, 10), 2.0) == (20, 20, 20)
    assert scale((10, 10, 10), 0.0) == (0, 0, 0)
