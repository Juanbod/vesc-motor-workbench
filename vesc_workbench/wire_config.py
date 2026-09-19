from pathlib import Path
import json
import math
import struct
import xml.etree.ElementTree as ET

LAYOUTS = json.loads(Path(__file__).with_name("fw602-layout.json").read_text(encoding="utf-8"))["layouts"]


def decode_config(data: bytes, kind: str) -> dict[str, float | int]:
    layout = LAYOUTS[kind]
    if len(data) != layout["size"] or struct.unpack_from(">I", data)[0] != layout["signature"]:
        raise ValueError(f"Unsupported {kind} configuration signature or size; refusing to patch.")
    result = {}
    for name, item in layout["fields"].items():
        value = struct.unpack_from(">" + item["format"], data, item["offset"])[0] / item["scale"]
        if not math.isfinite(value):
            raise ValueError(f"Non-finite configuration field {name}")
        result[name] = value
    return result


def patch_config(data: bytes, kind: str, changes: dict) -> bytes:
    decode_config(data, kind)
    output = bytearray(data)
    for name, value in changes.items():
        if not math.isfinite(value):
            raise ValueError(f"Non-finite patch {name}")
        item = LAYOUTS[kind]["fields"][name]
        encoded = value * item["scale"]
        if item["format"] != "f":
            encoded = round(encoded)
        struct.pack_into(">" + item["format"], output, item["offset"], encoded)
    return bytes(output)


def export_xml(data: bytes, kind: str, target: Path) -> None:
    root = ET.Element("MCConfiguration" if kind == "motor" else "APPConfiguration")
    for name, value in decode_config(data, kind).items():
        key = name.replace("[", "__").replace("]", "")
        ET.SubElement(root, key).text = format(value, ".9g")
    ET.indent(root)
    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)
