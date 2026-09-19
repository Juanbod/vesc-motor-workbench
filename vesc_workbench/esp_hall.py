from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic, sleep
import csv
import re


DEBUG_RE = re.compile(
    r"raw=(?P<raw>\d+)\s+sector=(?P<sector>[0-5])\s+status=0x(?P<status>[0-9a-fA-F]+)\s+magnet=(?P<magnet>\w+)"
)


@dataclass(frozen=True)
class EspHallSample:
    time_s: float
    raw: int
    angle_deg: float
    sector: int
    expected_sector: int
    status: str
    magnet: str
    line: str


def parse_debug_line(line: str, pole_pairs: int = 7, offset_counts: int = 0, reverse: bool = False) -> EspHallSample | None:
    match = DEBUG_RE.search(line.strip())
    if not match:
        return None
    raw = int(match.group("raw"))
    adjusted = (raw - offset_counts) % 4096
    if reverse:
        adjusted = (-adjusted) % 4096
    expected_sector = int(((adjusted * pole_pairs * 6) // 4096) % 6)
    return EspHallSample(
        time_s=0.0,
        raw=raw,
        angle_deg=raw * 360.0 / 4096.0,
        sector=int(match.group("sector")),
        expected_sector=expected_sector,
        status=f"0x{match.group('status').lower()}",
        magnet=match.group("magnet"),
        line=line.strip(),
    )


def monitor_esp_hall(
    port: str,
    baudrate: int,
    seconds: float,
    log_path: Path | None = None,
    pole_pairs: int = 7,
    offset_counts: int = 0,
    reverse: bool = False,
) -> int:
    try:
        import serial  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pyserial is required for ESP debug access. Install requirements.txt.") from exc

    fieldnames = list(EspHallSample.__annotations__)
    handle = None
    writer: csv.DictWriter[str] | None = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("w", newline="", encoding="utf-8")
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

    count = 0
    started = monotonic()
    try:
        with serial.Serial(port=port, baudrate=baudrate, timeout=0.2) as ser:
            ser.write(b"dbg 1\n")
            ser.flush()
            sleep(0.1)
            while monotonic() - started < seconds:
                raw_line = ser.readline()
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace").strip()
                sample = parse_debug_line(line, pole_pairs=pole_pairs, offset_counts=offset_counts, reverse=reverse)
                if sample is None:
                    continue
                sample = EspHallSample(
                    time_s=monotonic() - started,
                    raw=sample.raw,
                    angle_deg=sample.angle_deg,
                    sector=sample.sector,
                    expected_sector=sample.expected_sector,
                    status=sample.status,
                    magnet=sample.magnet,
                    line=sample.line,
                )
                mismatch = "!" if sample.sector != sample.expected_sector else " "
                print(
                    f"{sample.time_s:7.3f}s raw={sample.raw:4d} "
                    f"angle={sample.angle_deg:7.2f} sector={sample.sector} "
                    f"expected={sample.expected_sector}{mismatch} "
                    f"status={sample.status} magnet={sample.magnet}"
                )
                if writer is not None:
                    writer.writerow(asdict(sample))
                count += 1
    finally:
        try:
            with serial.Serial(port=port, baudrate=baudrate, timeout=0.2) as ser:
                ser.write(b"dbg 0\n")
                ser.flush()
        except Exception:
            pass
        if handle is not None:
            handle.close()

    return count

