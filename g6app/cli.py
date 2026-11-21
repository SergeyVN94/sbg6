"""Command line interface: ``g6 <command>``."""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import features as F
from .device import (
    FAMILY_DECODER,
    FAMILY_PLAYBACK,
    FAMILY_RECORDING,
    G6,
    OUTPUT_HEADPHONES,
    OUTPUT_SPEAKERS,
    G6Error,
    describe_permissions,
)
from .state import (
    State,
    apply_state,
    delete_profile,
    feature_key,
    list_profiles,
    load_last_state,
    load_profile,
    parse_feature_key,
    read_state,
    save_profile,
)

OUTPUT_BY_NAME = {"headphones": OUTPUT_HEADPHONES, "наушники": OUTPUT_HEADPHONES,
                  "speakers": OUTPUT_SPEAKERS, "колонки": OUTPUT_SPEAKERS}
OUTPUT_NAMES = {OUTPUT_HEADPHONES: "Наушники", OUTPUT_SPEAKERS: "Колонки"}
DAC_NAMES = dict(F.DAC_FILTERS)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fmt_bool(value: bool) -> str:
    return "вкл" if value else "выкл"


def _pct(value: float) -> str:
    return f"{round(value * 100):d}%"


def _db(value: float) -> str:
    return f"{value:+.1f} дБ"


def _eq_preset(name: str) -> F.EqPreset:
    for preset in F.EQ_PRESETS:
        if preset.name == name:
            return preset
    raise KeyError(name)


def _print_status(state: State) -> None:
    output = OUTPUT_NAMES.get(state.output, state.output)
    print(f"Sound BlasterX G6   прошивка {state.firmware or '?'}   выход: {output}")
    print(
        f"  SBX: {_fmt_bool(state.sbx):4}  Scout Mode: {_fmt_bool(state.scout):4}"
        f"  Direct: {_fmt_bool(state.direct)}"
    )
    print()
    for key, title, toggle, level, _ in F.EFFECTS:
        on = state.get(FAMILY_PLAYBACK, toggle) >= 0.5
        value = state.get(FAMILY_PLAYBACK, level)
        extra = ""
        if key == "smartvol":
            mode = int(round(state.get(FAMILY_PLAYBACK, F.PLAYBACK_SMARTVOL_MODE)))
            extra = f"  режим: {F.SMART_VOLUME_MODES[mode] if 0 <= mode < 3 else mode}"
        if key == "surround":
            extra = f"  дистанция: {state.get(FAMILY_PLAYBACK, F.PLAYBACK_SURROUND_DISTANCE):.0f} см"
        print(f"  {title:14} {_fmt_bool(on):4} {_pct(value)}{extra}")
    print()
    bands = " ".join(
        f"{label}:{gain:+.1f}" for label, gain in zip(F.EQ_LABELS, state.eq_bands(), strict=False)
    )
    print(f"  EQ {_fmt_bool(state.eq_enabled())}  preamp {_db(state.preamp())}  {bands}")
    print()
    print(
        f"  Микрофон: Voice Clarity {_fmt_bool(state.voice_clarity)} "
        f"{_pct(state.get(FAMILY_RECORDING, F.REC_NOISE_LEVEL) * 2)}  "
        f"буст {state.mic_boost} дБ  AEC {_fmt_bool(state.get(FAMILY_RECORDING, F.REC_AEC) >= 0.5)}"
    )
    print(f"  DAC-фильтр: {DAC_NAMES.get(state.dac_filter, state.dac_filter)}")
    color = "#{:02x}{:02x}{:02x}".format(*state.lighting_color)
    print(f"  Подсветка: {_fmt_bool(state.lighting_enabled)} {color}")


def _state_json(state: State) -> dict:
    return {
        "firmware": state.firmware,
        "output": OUTPUT_NAMES.get(state.output, state.output),
        "sbx": state.sbx,
        "scout": state.scout,
        "direct": state.direct,
        "effects": {
            key: {
                "enabled": state.get(FAMILY_PLAYBACK, toggle) >= 0.5,
                "level": round(state.get(FAMILY_PLAYBACK, level), 3),
            }
            for key, _, toggle, level, _ in F.EFFECTS
        },
        "equalizer": {
            "enabled": state.eq_enabled(),
            "preamp": state.preamp(),
            "bands": dict(zip(F.EQ_LABELS, state.eq_bands(), strict=False)),
        },
        "recording": {
            "voice_clarity": state.voice_clarity,
            "noise_level": round(state.get(FAMILY_RECORDING, F.REC_NOISE_LEVEL) * 2, 3),
            "mic_boost": state.mic_boost,
        },
        "dac_filter": state.dac_filter,
        "lighting": {"enabled": state.lighting_enabled, "color": state.lighting_color},
    }


def _connect(args) -> G6:
    device = G6(args.device)
    device.open()
    return device


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_status(args) -> int:
    with _connect(args) as device:
        state = read_state(device)
    if args.json:
        print(json.dumps(_state_json(state), ensure_ascii=False, indent=2))
    else:
        _print_status(state)
    return 0


def cmd_info(args) -> int:
    with _connect(args) as device:
        print(f"Устройство:  Sound BlasterX G6 ({device.path})")
        print(f"Прошивка:    {device.firmware() or '?'}")
        hw = device.hardware_id()
        print(f"Hardware ID: {hw:#04x}" if hw is not None else "Hardware ID: ?")
        print(f"Serial:      {device.serial() or '?'}")
        print(f"Ping:        {'ок' if device.ping() else 'нет ответа'}")
    return 0


def cmd_get(args) -> int:
    family, feature = parse_feature_key(args.feature)
    with _connect(args) as device:
        value = device.read_feature(family, feature)
    if value is None:
        print("Устройство не ответило", file=sys.stderr)
        return 1
    print(value)
    return 0


def cmd_set(args) -> int:
    family, feature = parse_feature_key(args.feature)
    with _connect(args) as device:
        if not device.write_feature(family, feature, args.value):
            print("Устройство отклонило команду", file=sys.stderr)
            return 1
    return 0


def _toggle(args, setter) -> int:
    with _connect(args) as device:
        setter(device, args.state == "on")
    return 0


def cmd_sbx(args) -> int:
    return _toggle(args, lambda d, on: d.set_global(1, on))


def cmd_scout(args) -> int:
    return _toggle(args, lambda d, on: d.set_global(2, on))


def cmd_direct(args) -> int:
    return _toggle(args, lambda d, on: d.set_direct_mode(on))


def cmd_output(args) -> int:
    with _connect(args) as device:
        if args.mode == "toggle":
            current = device.read_output()
            mode = OUTPUT_SPEAKERS if current == OUTPUT_HEADPHONES else OUTPUT_HEADPHONES
        else:
            mode = OUTPUT_BY_NAME[args.mode]
        device.set_output(mode)
    return 0


def cmd_eq(args) -> int:
    with _connect(args) as device:
        if args.preset:
            preset = _eq_preset(args.preset)
            device.write_feature(FAMILY_PLAYBACK, F.PLAYBACK_EQ_PREAMP, preset.preamp)
            for band, gain in zip(F.PLAYBACK_EQ_BANDS, preset.bands, strict=False):
                device.write_feature(FAMILY_PLAYBACK, band, gain)
            print(f"Пресет «{preset.title}» применён")
        if args.bands:
            values = _parse_bands(args.bands)
            for band, gain in zip(F.PLAYBACK_EQ_BANDS, values, strict=False):
                device.write_feature(FAMILY_PLAYBACK, band, gain)
        if args.preamp is not None:
            device.write_feature(FAMILY_PLAYBACK, F.PLAYBACK_EQ_PREAMP, args.preamp)
        if args.on:
            device.write_feature(FAMILY_PLAYBACK, F.PLAYBACK_EQ_TOGGLE, 1.0)
        elif args.off:
            device.write_feature(FAMILY_PLAYBACK, F.PLAYBACK_EQ_TOGGLE, 0.0)
    return 0


def _parse_bands(tokens: list[str]) -> list[float]:
    if len(tokens) == 1 and "," in tokens[0]:
        tokens = tokens[0].split(",")
    if len(tokens) == len(F.EQ_FREQUENCIES):
        try:
            return [float(t) for t in tokens]
        except ValueError:
            pass
    gains = [0.0] * len(F.EQ_FREQUENCIES)
    for token in tokens:
        label, _, value = token.partition("=")
        key = label.strip().lower().replace("hz", "")
        if key not in [str(f) for f in F.EQ_FREQUENCIES] and key not in [
            lbl.lower() for lbl in F.EQ_LABELS
        ]:
            raise SystemExit(f"Неизвестная полоса: {label}")
        index = [str(f) for f in F.EQ_FREQUENCIES].index(key) if key in [
            str(f) for f in F.EQ_FREQUENCIES
        ] else [lbl.lower() for lbl in F.EQ_LABELS].index(key)
        gains[index] = float(value)
    return gains


def cmd_mic_boost(args) -> int:
    with _connect(args) as device:
        device.set_mic_boost(args.db)
    return 0


def cmd_dac(args) -> int:
    with _connect(args) as device:
        device.set_dac_filter(args.filter)
    return 0


def cmd_lighting(args) -> int:
    with _connect(args) as device:
        if args.action in ("on", "off"):
            device.set_lighting_enabled(args.action == "on")
        elif args.action == "color":
            value = args.color.lstrip("#")
            if len(value) != 6:
                raise SystemExit("Цвет задаётся как #rrggbb")
            device.set_lighting_color(
                int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
            )
    return 0


def cmd_profile(args) -> int:
    if args.action == "list":
        names = list_profiles()
        if not names:
            print("Профилей нет")
        for name in names:
            print(name)
        return 0
    if args.action == "save":
        device = G6(args.device)
        with device:
            state = read_state(device)
        path = save_profile(args.name, state)
        print(f"Сохранено: {path}")
        return 0
    if args.action == "load":
        state = load_profile(args.name)
        with _connect(args) as device:
            apply_state(device, state)
        print(f"Профиль «{args.name}» применён")
        return 0
    if args.action == "delete":
        print("Удалён" if delete_profile(args.name) else "Профиль не найден")
        return 0
    return 1


def cmd_restore(args) -> int:
    """Apply the last saved state; used by the systemd user unit."""
    state = load_last_state()
    if state is None:
        print("Нет сохранённого состояния — нечего восстанавливать")
        return 0
    deadline = time.monotonic() + args.wait
    while True:
        try:
            with G6(args.device) as device:
                apply_state(device, state)
            print("Состояние G6 восстановлено")
            return 0
        except G6Error as exc:
            if time.monotonic() >= deadline:
                print(f"G6 не найден: {exc}", file=sys.stderr)
                return 1
            time.sleep(2)


def cmd_gui(args) -> int:
    from .gui.app import main as gui_main

    return gui_main(["--device", args.device] if args.device else [])


def cmd_raw(args) -> int:
    data = bytes.fromhex(args.hex.replace(" ", ""))
    with _connect(args) as device:
        device.send(data[1] if len(data) > 1 else 0, data[3:])
        frame = device.wait_for(lambda f: True, timeout=0.5)
        print(frame or "нет ответа")
    return 0


def cmd_dump(args) -> int:
    with _connect(args) as device:
        out = {}
        for family in (FAMILY_PLAYBACK, FAMILY_RECORDING, FAMILY_DECODER):
            for feature in range(0x40):
                value = device.read_feature(family, feature, timeout=0.2)
                if value:
                    out[feature_key(family, feature)] = value
    print(json.dumps(out, indent=2))
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="g6",
        description="Управление Sound BlasterX G6 (SB1770) в Linux",
    )
    parser.add_argument("-d", "--device", help="путь к /dev/hidrawN (по умолчанию — автопоиск)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="показать текущее состояние")
    p.add_argument("--json", action="store_true", help="вывод в JSON")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("info", help="прошивка, серийный номер, связь")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("get", help="прочитать параметр, например 96:07")
    p.add_argument("feature")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("set", help="записать параметр, например 96:07 1")
    p.add_argument("feature")
    p.add_argument("value", type=float)
    p.set_defaults(func=cmd_set)

    for name, func, text in (
        ("sbx", cmd_sbx, "включить/выключить SBX"),
        ("scout", cmd_scout, "включить/выключить Scout Mode"),
        ("direct", cmd_direct, "включить/выключить Direct Mode"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("state", choices=("on", "off"))
        p.set_defaults(func=func)

    p = sub.add_parser("output", help="выход: наушники или колонки")
    p.add_argument("mode", choices=("headphones", "speakers", "toggle"))
    p.set_defaults(func=cmd_output)

    p = sub.add_parser("eq", help="эквалайзер: полосы, пресет, включение")
    p.add_argument("bands", nargs="*", help="10 значений в дБ или пары вида 1k=+3")
    p.add_argument("--preset", help=", ".join(p_.name for p_ in F.EQ_PRESETS))
    p.add_argument("--preamp", type=float, help="-6…+6 дБ")
    p.add_argument("--on", action="store_true", help="включить эквалайзер")
    p.add_argument("--off", action="store_true", help="выключить эквалайзер")
    p.set_defaults(func=cmd_eq)

    p = sub.add_parser("mic-boost", help="усиление микрофона")
    p.add_argument("db", type=int, choices=F.MIC_BOOST_VALUES)
    p.set_defaults(func=cmd_mic_boost)

    p = sub.add_parser("dac-filter", help="цифровой фильтр ЦАП")
    p.add_argument("filter", type=int, choices=[value for value, _ in F.DAC_FILTERS])
    p.set_defaults(func=cmd_dac)

    p = sub.add_parser("lighting", help="подсветка")
    p.add_argument("action", choices=("on", "off", "color"))
    p.add_argument("color", nargs="?", default="#ffffff")
    p.set_defaults(func=cmd_lighting)

    p = sub.add_parser("profile", help="профили")
    p.add_argument("action", choices=("list", "save", "load", "delete"))
    p.add_argument("name", nargs="?")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("restore", help="восстановить последнее состояние (для systemd)")
    p.add_argument("--wait", type=int, default=0, help="ждать появления устройства, сек")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("dump", help="снять все известные регистры (отладка)")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("raw", help="отправить произвольный кадр (отладка)")
    p.add_argument("hex")
    p.set_defaults(func=cmd_raw)

    p = sub.add_parser("gui", help="открыть окно приложения")
    p.set_defaults(func=cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    is_profile_write = getattr(args, "command", None) == "profile" and args.action in (
        "save",
        "load",
        "delete",
    )
    if is_profile_write and not args.name:
        parser.error("укажите имя профиля")
    try:
        return args.func(args)
    except G6Error as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        hint = describe_permissions(args.device)
        if hint:
            print(hint, file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    except KeyError as exc:
        print(f"Неизвестный пресет: {exc.args[0]}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
