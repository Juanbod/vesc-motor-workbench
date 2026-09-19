from __future__ import annotations

from datetime import datetime
from dataclasses import asdict
from pathlib import Path
from time import sleep
import argparse
import json
import shutil
import sys

from .appliers import ConfigApplyError, make_applier
from .autotest import SafetyLimits, parse_steps, run_current_ramp
from .autotune import generate_autotune_queue, load_autotune_matrix, run_autotune_queue
from .configs import ConfigError, ConfigManager, validate_xml_file
from .esp_hall import monitor_esp_hall
from .raw_config import backup_raw_config, restore_raw_config
from .raw_variants import generate_default_raw_variants, upload_raw_variant_queue
from .settings import ensure_project_dirs, load_settings
from .uart import VescUartClient
from .bench import add_commands as add_bench_commands


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _manager() -> ConfigManager:
    settings = load_settings()
    ensure_project_dirs(settings)
    return ConfigManager(
        root=settings.root,
        incoming=settings.paths.incoming,
        staged=settings.paths.staged,
        applied=settings.paths.applied,
    )


def cmd_init(args: argparse.Namespace) -> int:
    settings = load_settings()
    ensure_project_dirs(settings)
    example = settings.root / "config" / "settings.example.toml"
    target = settings.root / "config" / "settings.toml"
    if example.exists() and not target.exists():
        shutil.copy2(example, target)
        print(f"Created {target}")
    elif target.exists():
        print(f"Settings already exist: {target}")
    else:
        print("Project directories are ready.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    settings = load_settings()
    ensure_project_dirs(settings)
    _print_json(
        {
            "root": str(settings.root),
            "serial": asdict(settings.serial),
            "paths": {key: str(value) for key, value in asdict(settings.paths).items()},
            "apply": asdict(settings.apply),
            "safety": asdict(settings.safety),
        }
    )
    return 0


def cmd_validate_config(args: argparse.Namespace) -> int:
    config = validate_xml_file(Path(args.file), forced_kind=args.kind)
    _print_json(
        {
            "path": config.path,
            "kind": config.kind,
            "sha256": config.sha256,
            "root_tag": config.root_tag,
            "warnings": config.warnings,
        }
    )
    return 0


def cmd_import_config(args: argparse.Namespace) -> int:
    manager = _manager()
    imported = manager.import_config(Path(args.file), profile=args.profile)
    print(f"Imported config to {imported}")
    return 0


def cmd_scan_configs(args: argparse.Namespace) -> int:
    manager = _manager()
    settings = load_settings()
    applier = make_applier(args.backend or settings.apply.backend, settings.apply.vesc_tool_path)

    while True:
        bundles = manager.stage_new_configs()
        if not bundles:
            print("No new XML configs found.")
        for bundle in bundles:
            print(f"Staged {bundle.bundle_id}: {len(bundle.files)} file(s) at {bundle.path}")
            if args.auto_apply:
                result = applier.apply(bundle, armed=args.armed)
                manager.mark_applied(bundle, result.to_dict())
                print(result.message)
        if args.once:
            return 0
        sleep(args.interval)


def cmd_apply_config(args: argparse.Namespace) -> int:
    manager = _manager()
    settings = load_settings()
    backend = args.backend or settings.apply.backend
    applier = make_applier(backend, settings.apply.vesc_tool_path)
    bundle = manager.load_bundle(args.bundle)
    result = applier.apply(bundle, armed=args.armed)
    manager.mark_applied(bundle, result.to_dict())
    print(result.message)
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    settings = load_settings()
    port = args.port or settings.serial.port
    with VescUartClient(
        port=port,
        baudrate=args.baudrate or settings.serial.baudrate,
        timeout_s=settings.serial.timeout_s,
    ) as client:
        while True:
            values = client.get_values()
            print(
                f"erpm={values.erpm:>7} iq={values.iq_a:>7.2f}A "
                f"motor={values.current_motor_a:>7.2f}A duty={values.duty:>6.3f} "
                f"vin={values.v_in:>5.1f}V fault={values.fault_code}"
            )
            sleep(args.interval)


def cmd_test_current(args: argparse.Namespace) -> int:
    settings = load_settings()
    steps = parse_steps(args.steps) if args.steps else settings.safety.default_current_steps
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = settings.paths.logs / f"current-ramp-{stamp}.csv"
    result = run_current_ramp(
        port=args.port or settings.serial.port,
        baudrate=args.baudrate or settings.serial.baudrate,
        timeout_s=settings.serial.timeout_s,
        steps=steps,
        hold_s=args.hold,
        limits=SafetyLimits(
            max_erpm=args.max_erpm,
            max_erpm_delta=args.max_erpm_delta,
            sample_period_s=args.sample_period,
            max_motor_current_a=args.max_motor_current,
            max_input_current_a=args.max_input_current,
            max_mos_temp_c=args.max_mos_temp,
            max_motor_temp_c=args.max_motor_temp,
            max_duty=args.max_duty,
        ),
        log_path=log_path,
        armed=args.armed,
    )
    print(f"log={result.log_path}")
    print(f"completed={result.completed}")
    print(f"stop_reason={result.stop_reason}")
    return 0 if result.completed else 2


def _limits_from_args(args: argparse.Namespace) -> SafetyLimits:
    return SafetyLimits(
        max_erpm=args.max_erpm,
        max_erpm_delta=args.max_erpm_delta,
        sample_period_s=args.sample_period,
        max_motor_current_a=args.max_motor_current,
        max_input_current_a=args.max_input_current,
        max_mos_temp_c=args.max_mos_temp,
        max_motor_temp_c=args.max_motor_temp,
        max_duty=args.max_duty,
    )


def cmd_generate_autotune_queue(args: argparse.Namespace) -> int:
    settings = load_settings()
    output = Path(args.output_dir) if args.output_dir else settings.root / "autotune-queue"
    generated = generate_autotune_queue(Path(args.base_backup), Path(args.matrix), output)
    for item in generated:
        print(f"generated={item}")
    return 0


def cmd_autotune_run(args: argparse.Namespace) -> int:
    settings = load_settings()
    plan, _ = load_autotune_matrix(Path(args.matrix))
    run_dir = run_autotune_queue(
        queue_root=Path(args.queue_dir),
        plan=plan,
        port=args.port or settings.serial.port,
        baudrate=args.baudrate or settings.serial.baudrate,
        timeout_s=settings.serial.timeout_s,
        limits=_limits_from_args(args),
        logs_root=settings.paths.logs,
        armed=args.armed,
        max_profiles=args.max_profiles,
    )
    print(f"run={run_dir}")
    return 0


def cmd_esp_hall_monitor(args: argparse.Namespace) -> int:
    settings = load_settings()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = Path(args.log) if args.log else settings.paths.logs / f"esp-hall-debug-{stamp}.csv"
    count = monitor_esp_hall(
        port=args.port,
        baudrate=args.baudrate,
        seconds=args.seconds,
        log_path=log_path,
        pole_pairs=args.pole_pairs,
        offset_counts=args.offset_counts,
        reverse=args.reverse,
    )
    print(f"samples={count}")
    print(f"log={log_path.resolve()}")
    return 0


def cmd_fw_version(args: argparse.Namespace) -> int:
    settings = load_settings()
    with VescUartClient(
        port=args.port or settings.serial.port,
        baudrate=args.baudrate or settings.serial.baudrate,
        timeout_s=settings.serial.timeout_s,
    ) as client:
        version = client.fw_version()
    _print_json(asdict(version))
    return 0


def cmd_backup_raw_config(args: argparse.Namespace) -> int:
    settings = load_settings()
    output_dir = settings.root / "raw-config-backups"
    path = backup_raw_config(
        port=args.port or settings.serial.port,
        baudrate=args.baudrate or settings.serial.baudrate,
        timeout_s=settings.serial.timeout_s,
        output_dir=output_dir,
        name=args.name,
    )
    print(f"backup={path}")
    return 0


def cmd_restore_raw_config(args: argparse.Namespace) -> int:
    settings = load_settings()
    kinds = tuple(args.kind.split(","))
    result = restore_raw_config(
        port=args.port or settings.serial.port,
        baudrate=args.baudrate or settings.serial.baudrate,
        timeout_s=settings.serial.timeout_s,
        backup_dir=Path(args.backup),
        kinds=kinds,
        armed=args.armed,
    )
    _print_json(result)
    return 0


def cmd_generate_raw_variants(args: argparse.Namespace) -> int:
    settings = load_settings()
    base_backup = Path(args.base_backup)
    output_root = Path(args.output_dir) if args.output_dir else settings.root / "raw-config-variants"
    generated = generate_default_raw_variants(base_backup=base_backup, output_root=output_root)
    for path in generated:
        print(f"generated={path}")
    return 0


def cmd_upload_raw_variant_queue(args: argparse.Namespace) -> int:
    settings = load_settings()
    kinds = tuple(args.kind.split(","))
    result = upload_raw_variant_queue(
        queue_root=Path(args.queue_dir),
        port=args.port or settings.serial.port,
        baudrate=args.baudrate or settings.serial.baudrate,
        timeout_s=settings.serial.timeout_s,
        armed=args.armed,
        wait_s=args.wait,
        kinds=kinds,
    )
    _print_json(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vesc-workbench")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create local settings and required folders.")
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status", help="Show current project settings.")
    status.set_defaults(func=cmd_status)

    validate = sub.add_parser("validate-config", help="Validate one VESC XML file.")
    validate.add_argument("file")
    validate.add_argument("--kind", choices=["auto", "app", "motor", "unknown"], default="auto")
    validate.set_defaults(func=cmd_validate_config)

    import_config = sub.add_parser("import-config", help="Copy one XML file into profiles/incoming.")
    import_config.add_argument("file")
    import_config.add_argument("--profile")
    import_config.set_defaults(func=cmd_import_config)

    scan = sub.add_parser("scan-configs", help="Stage new XML files from profiles/incoming.")
    scan.add_argument("--once", action=argparse.BooleanOptionalAction, default=True)
    scan.add_argument("--interval", type=float, default=2.0)
    scan.add_argument("--auto-apply", action="store_true")
    scan.add_argument("--armed", action="store_true")
    scan.add_argument("--backend", choices=["dry-run", "uart-xml", "vesc-tool-open"])
    scan.set_defaults(func=cmd_scan_configs)

    apply_config = sub.add_parser("apply-config", help="Apply or dry-run one staged bundle.")
    apply_config.add_argument("bundle")
    apply_config.add_argument("--armed", action="store_true")
    apply_config.add_argument("--backend", choices=["dry-run", "uart-xml", "vesc-tool-open"])
    apply_config.set_defaults(func=cmd_apply_config)

    monitor = sub.add_parser("monitor", help="Print VESC GET_VALUES repeatedly.")
    monitor.add_argument("--port")
    monitor.add_argument("--baudrate", type=int)
    monitor.add_argument("--interval", type=float, default=0.2)
    monitor.set_defaults(func=cmd_monitor)

    test = sub.add_parser("test-current", help="Run guarded UART current ramp.")
    test.add_argument("--port")
    test.add_argument("--baudrate", type=int)
    test.add_argument("--steps", help="Comma-separated amps, for example: 0.5,1.0,1.5")
    test.add_argument("--hold", type=float, default=1.0)
    test.add_argument("--max-erpm", type=int, default=1000)
    test.add_argument("--max-erpm-delta", type=int, default=500)
    test.add_argument("--sample-period", type=float, default=0.05)
    test.add_argument("--max-motor-current", type=float, default=100.0)
    test.add_argument("--max-input-current", type=float, default=110.0)
    test.add_argument("--max-mos-temp", type=float, default=80.0)
    test.add_argument("--max-motor-temp", type=float, default=100.0)
    test.add_argument("--max-duty", type=float, default=0.95)
    test.add_argument("--armed", action="store_true")
    test.set_defaults(func=cmd_test_current)

    esp = sub.add_parser("esp-hall-monitor", help="Monitor AS5600+ESP8266 Hall emulator debug output.")
    esp.add_argument("--port", default="COM6")
    esp.add_argument("--baudrate", type=int, default=115200)
    esp.add_argument("--seconds", type=float, default=10.0)
    esp.add_argument("--log")
    esp.add_argument("--pole-pairs", type=int, default=7)
    esp.add_argument("--offset-counts", type=int, default=0)
    esp.add_argument("--reverse", action="store_true")
    esp.set_defaults(func=cmd_esp_hall_monitor)

    fw = sub.add_parser("fw-version", help="Read VESC firmware and hardware version.")
    fw.add_argument("--port")
    fw.add_argument("--baudrate", type=int)
    fw.set_defaults(func=cmd_fw_version)

    backup = sub.add_parser("backup-raw-config", help="Read binary mcconf/appconf from VESC into a backup folder.")
    backup.add_argument("--port")
    backup.add_argument("--baudrate", type=int)
    backup.add_argument("--name", default="profile17")
    backup.set_defaults(func=cmd_backup_raw_config)

    restore = sub.add_parser("restore-raw-config", help="Write a previously backed-up binary config to VESC.")
    restore.add_argument("backup")
    restore.add_argument("--port")
    restore.add_argument("--baudrate", type=int)
    restore.add_argument("--kind", choices=["motor", "app", "motor,app", "app,motor"], default="motor,app")
    restore.add_argument("--armed", action="store_true")
    restore.set_defaults(func=cmd_restore_raw_config)

    variants = sub.add_parser("generate-raw-variants", help="Generate uploadable binary variants from a raw backup.")
    variants.add_argument("base_backup")
    variants.add_argument("--output-dir")
    variants.set_defaults(func=cmd_generate_raw_variants)

    upload_queue = sub.add_parser("upload-raw-variant-queue", help="Upload every raw variant in a queue directory.")
    upload_queue.add_argument("queue_dir")
    upload_queue.add_argument("--port")
    upload_queue.add_argument("--baudrate", type=int)
    upload_queue.add_argument("--kind", choices=["motor", "app", "motor,app", "app,motor"], default="motor,app")
    upload_queue.add_argument("--wait", type=float, default=1.0)
    upload_queue.add_argument("--armed", action="store_true")
    upload_queue.set_defaults(func=cmd_upload_raw_variant_queue)

    autotune_queue = sub.add_parser(
        "generate-autotune-queue",
        help="Generate a direct-encoder raw tuning queue from a detected raw backup.",
    )
    autotune_queue.add_argument("base_backup")
    autotune_queue.add_argument("matrix")
    autotune_queue.add_argument("--output-dir")
    autotune_queue.set_defaults(func=cmd_generate_autotune_queue)

    autotune_run = sub.add_parser(
        "autotune-run",
        help="Restore, test, record and score each profile in an autotune queue.",
    )
    autotune_run.add_argument("queue_dir")
    autotune_run.add_argument("matrix")
    autotune_run.add_argument("--port")
    autotune_run.add_argument("--baudrate", type=int)
    autotune_run.add_argument("--max-profiles", type=int)
    autotune_run.add_argument("--max-erpm", type=int, default=1000)
    autotune_run.add_argument("--max-erpm-delta", type=int, default=500)
    autotune_run.add_argument("--sample-period", type=float, default=0.05)
    autotune_run.add_argument("--max-motor-current", type=float, default=30.0)
    autotune_run.add_argument("--max-input-current", type=float, default=30.0)
    autotune_run.add_argument("--max-mos-temp", type=float, default=80.0)
    autotune_run.add_argument("--max-motor-temp", type=float, default=100.0)
    autotune_run.add_argument("--max-duty", type=float, default=0.80)
    autotune_run.add_argument("--armed", action="store_true")
    autotune_run.set_defaults(func=cmd_autotune_run)

    add_bench_commands(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, ConfigApplyError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
