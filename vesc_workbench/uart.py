from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from struct import pack, unpack_from
from typing import BinaryIO
from time import sleep, perf_counter as monotonic
import math
from collections import deque
from .fixture import check_payload


class VescCommand(IntEnum):
    COMM_FW_VERSION = 0
    COMM_GET_VALUES = 4
    COMM_SET_DUTY = 5
    COMM_SET_CURRENT = 6
    COMM_SET_CURRENT_BRAKE = 7
    COMM_SET_RPM = 8
    COMM_SET_DETECT = 11
    COMM_SET_MCCONF = 13
    COMM_GET_MCCONF = 14
    COMM_SET_APPCONF = 16
    COMM_GET_APPCONF = 17
    COMM_ALIVE = 30
    COMM_SET_APPCONF_NO_STORE = 149


class VescPacketError(RuntimeError):
    pass


@dataclass(frozen=True)
class VescValues:
    temp_mos_c: float
    temp_motor_c: float
    current_motor_a: float
    current_in_a: float
    id_a: float
    iq_a: float
    duty: float
    erpm: int
    v_in: float
    fault_code: int
    tachometer: int = 0
    tachometer_abs: int = 0


@dataclass(frozen=True)
class VescFirmwareVersion:
    major: int
    minor: int
    hardware: str


def crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def encode_packet(payload: bytes) -> bytes:
    length = len(payload)
    if length <= 255:
        header = bytes((2, length))
    elif length <= 65535:
        header = bytes((3, (length >> 8) & 0xFF, length & 0xFF))
    else:
        raise VescPacketError("Payload is too large for a VESC UART packet.")

    crc = crc16(payload)
    return header + payload + pack(">H", crc) + bytes((3,))


def extract_packet(frame: bytes) -> bytes:
    if not frame:
        raise VescPacketError("Empty frame.")
    start = frame[0]
    if start == 2:
        if len(frame) < 5:
            raise VescPacketError("Short VESC frame.")
        length = frame[1]
        payload_start = 2
    elif start == 3:
        if len(frame) < 6:
            raise VescPacketError("Short VESC long frame.")
        length = (frame[1] << 8) | frame[2]
        payload_start = 3
    else:
        raise VescPacketError(f"Unexpected VESC packet start byte: {start}")

    payload_end = payload_start + length
    expected_len = payload_end + 3
    if len(frame) != expected_len:
        raise VescPacketError(f"Frame length mismatch: got {len(frame)}, expected {expected_len}.")
    if frame[-1] != 3:
        raise VescPacketError("Invalid VESC frame stop byte.")

    payload = frame[payload_start:payload_end]
    received_crc = unpack_from(">H", frame, payload_end)[0]
    actual_crc = crc16(payload)
    if received_crc != actual_crc:
        raise VescPacketError(f"CRC mismatch: got 0x{received_crc:04x}, expected 0x{actual_crc:04x}.")
    return payload


def command_payload(command: VescCommand, body: bytes = b"") -> bytes:
    return bytes((int(command),)) + body


def set_current_payload(current_a: float) -> bytes:
    value = int(round(current_a * 1000.0))
    return command_payload(VescCommand.COMM_SET_CURRENT, pack(">i", value))


def alive_payload() -> bytes:
    return command_payload(VescCommand.COMM_ALIVE)


def get_values_payload() -> bytes:
    return command_payload(VescCommand.COMM_GET_VALUES)


def fw_version_payload() -> bytes:
    return command_payload(VescCommand.COMM_FW_VERSION)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def int16(self, scale: float = 1.0) -> float:
        value = unpack_from(">h", self.data, self.offset)[0]
        self.offset += 2
        return value / scale

    def uint8(self) -> int:
        value = self.data[self.offset]
        self.offset += 1
        return value

    def int32(self, scale: float = 1.0) -> float:
        value = unpack_from(">i", self.data, self.offset)[0]
        self.offset += 4
        return value / scale


def parse_values_payload(payload: bytes) -> VescValues:
    if not payload or payload[0] != VescCommand.COMM_GET_VALUES:
        raise VescPacketError("Payload is not a COMM_GET_VALUES response.")
    if len(payload) < 54:
        raise VescPacketError("Truncated COMM_GET_VALUES response.")
    reader = _Reader(payload[1:])
    temp_mos = reader.int16(10.0)
    temp_motor = reader.int16(10.0)
    current_motor = reader.int32(100.0)
    current_in = reader.int32(100.0)
    id_a = reader.int32(100.0)
    iq_a = reader.int32(100.0)
    duty = reader.int16(1000.0)
    erpm = int(reader.int32(1.0))
    v_in = reader.int16(10.0)
    reader.int32(10000.0)  # amp hours
    reader.int32(10000.0)  # amp hours charged
    reader.int32(10000.0)  # watt hours
    reader.int32(10000.0)  # watt hours charged
    tachometer = int(reader.int32())
    tachometer_abs = int(reader.int32())
    fault_code = reader.uint8()
    return VescValues(
        temp_mos_c=temp_mos,
        temp_motor_c=temp_motor,
        current_motor_a=current_motor,
        current_in_a=current_in,
        id_a=id_a,
        iq_a=iq_a,
        duty=duty,
        erpm=erpm,
        v_in=v_in,
        fault_code=fault_code,
        tachometer=tachometer,
        tachometer_abs=tachometer_abs,
    )


def parse_fw_version_payload(payload: bytes) -> VescFirmwareVersion:
    if len(payload) < 3 or payload[0] != VescCommand.COMM_FW_VERSION:
        raise VescPacketError("Payload is not a COMM_FW_VERSION response.")
    hardware_bytes = payload[3:].split(b"\0", 1)[0]
    return VescFirmwareVersion(
        major=payload[1],
        minor=payload[2],
        hardware=hardware_bytes.decode("utf-8", errors="replace"),
    )


def parse_pid_position_payload(payload: bytes) -> float | None:
    # Firmware 6.02 GET_VALUES: the position extension follows byte 53 (fault).
    if not payload or payload[0] != VescCommand.COMM_GET_VALUES:
        raise VescPacketError('Position requires a GET_VALUES response')
    if len(payload) < 58:
        return None
    return unpack_from('>i', payload, 54)[0] / 1e6


class AvailableSerialReader:
    """Cache only bytes already available, with at most one backend read per call."""
    def __init__(self, stream):
        self.stream = stream
        self.buffer = bytearray()

    def read(self, size):
        if size < 0:
            raise ValueError('A bounded read size is required')
        if len(self.buffer) < size:
            available = min(4096, max(0, self.stream.in_waiting))
            self.buffer.extend(self.stream.read(max(size-len(self.buffer), available)))
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result


class VescUartClient:
    def __init__(self, port: str, baudrate: int = 115200, timeout_s: float = 0.1,
                 *, buffered_rx: bool = False) -> None:
        try:
            import serial  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("pyserial is required for UART access. Install requirements.txt.") from exc

        self.serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout_s, write_timeout=timeout_s)
        self._reader = AvailableSerialReader(self.serial) if buffered_rx else self.serial
        self.response_timeout_s = max(0.5, timeout_s * 4)
        self.rotor_angle: float | None = None
        self.rotor_received_at = 0.0
        self.rotor_samples: deque[tuple[float, float]] = deque(maxlen=2048)
        self.position_mode = 0
        self.pid_position = None
        self.pid_received_at = 0.0
        self.observer_error = None
        self.observer_received_at = 0.0

    def close(self) -> None:
        self.serial.close()

    def __enter__(self) -> "VescUartClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def send_payload(self, payload: bytes) -> None:
        check_payload(payload)
        self.serial.write(encode_packet(payload))

    def read_payload(self) -> bytes:
        frame = read_frame(getattr(self, '_reader', self.serial))
        payload = extract_packet(frame)
        if payload and payload[0] == 22 and len(payload) == 5:
            value = unpack_from('>i', payload, 1)[0] / 100000.0
            if getattr(self, 'position_mode', 3) == 6:
                self.observer_error = value
                self.observer_received_at = monotonic()
            elif getattr(self, 'position_mode', 3) == 3:
                self.rotor_angle = value
                self.rotor_received_at = monotonic()
                self.rotor_samples.append((self.rotor_received_at, self.rotor_angle))
        return payload

    def read_response(self, command: int) -> bytes:
        deadline = monotonic() + self.response_timeout_s
        while monotonic() < deadline:
            payload = self.read_payload()
            if payload and payload[0] == command:
                return payload
        raise VescPacketError(f"Timed out waiting for response {command}.")

    def stream_encoder(self, enabled: bool) -> None:
        self.set_position_stream(3 if enabled else 0)

    def set_position_stream(self, mode: int) -> None:
        if mode not in (0, 3, 6):
            raise ValueError('Only none, raw encoder, and observer-error display modes are supported')
        self.position_mode = mode
        self.observer_error, self.observer_received_at = None, 0.0
        self.send_payload(command_payload(VescCommand.COMM_SET_DETECT, bytes((mode,))))

    def set_rpm(self, erpm: float) -> None:
        self.send_payload(command_payload(VescCommand.COMM_SET_RPM, pack(">i", round(erpm))))

    def set_app_config_temporary(self, data: bytes) -> None:
        self.send_payload(command_payload(VescCommand.COMM_SET_APPCONF_NO_STORE, data))
        self.read_response(VescCommand.COMM_SET_APPCONF_NO_STORE)

    def alive(self) -> None:
        self.send_payload(alive_payload())

    def set_current(self, current_a: float) -> None:
        if not math.isfinite(current_a):
            raise ValueError("Current must be finite.")
        self.send_payload(set_current_payload(current_a))

    def get_values(self) -> VescValues:
        self.send_payload(get_values_payload())
        payload = self.read_response(VescCommand.COMM_GET_VALUES)
        values = parse_values_payload(payload)
        self.pid_position = parse_pid_position_payload(payload)
        self.pid_received_at = monotonic() if self.pid_position is not None else 0.0
        return values

    def fw_version(self) -> VescFirmwareVersion:
        self.send_payload(fw_version_payload())
        return parse_fw_version_payload(self.read_response(VescCommand.COMM_FW_VERSION))

    def get_raw_config(self, kind: str) -> bytes:
        command = {
            "motor": VescCommand.COMM_GET_MCCONF,
            "app": VescCommand.COMM_GET_APPCONF,
        }.get(kind)
        if command is None:
            raise VescPacketError(f"Unknown raw config kind: {kind}")
        self.send_payload(command_payload(command))
        payload = self.read_response(command)
        if not payload or payload[0] != command:
            got = payload[0] if payload else None
            raise VescPacketError(f"Unexpected raw config response for {kind}: got {got}, expected {int(command)}.")
        sleep(0.1)
        return payload[1:]

    def set_raw_config(self, kind: str, data: bytes) -> None:
        command = {
            "motor": VescCommand.COMM_SET_MCCONF,
            "app": VescCommand.COMM_SET_APPCONF,
        }.get(kind)
        if command is None:
            raise VescPacketError(f"Unknown raw config kind: {kind}")
        self.send_payload(command_payload(command, data))


def read_frame(stream: BinaryIO) -> bytes:
    start = stream.read(1)
    if not start:
        raise VescPacketError("Timed out waiting for VESC packet.")

    start_byte = start[0]
    if start_byte == 2:
        length_data = stream.read(1)
        if len(length_data) != 1:
            raise VescPacketError("Timed out reading VESC packet length.")
        length = length_data[0]
        header = start + length_data
    elif start_byte == 3:
        length_data = stream.read(2)
        if len(length_data) != 2:
            raise VescPacketError("Timed out reading VESC long packet length.")
        length = (length_data[0] << 8) | length_data[1]
        header = start + length_data
    else:
        raise VescPacketError(f"Unexpected VESC packet start byte: {start_byte}")

    rest = stream.read(length + 3)
    if len(rest) != length + 3:
        raise VescPacketError("Timed out reading full VESC packet.")
    return header + rest
