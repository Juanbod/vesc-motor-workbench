"""Generate a wire layout from the pinned upstream serializer, without guessing offsets."""
from pathlib import Path
import json
import re
import subprocess
import sys

REF = "f7c2b34e1cff2234cae98be3abf0cd50e249558f"
source = subprocess.check_output(["git", "-C", sys.argv[1], "show", f"{REF}:confgenerator.c"], text=True)
header = subprocess.check_output(["git", "-C", sys.argv[1], "show", f"{REF}:confgenerator.h"], text=True)
layouts = {}
for kind, name in (("motor", "mcconf"), ("app", "appconf")):
    body = source.split(f"int32_t confgenerator_serialize_{name}(", 1)[1].split("return ind;", 1)[0]
    offset = 4
    fields = {}
    for line in body.splitlines():
        if "conf->" not in line:
            continue
        byte = re.fullmatch(r"\s*buffer\[ind\+\+\] = (?:\(uint8_t\))?conf->([\w.\[\]]+);", line)
        call = re.fullmatch(r"\s*buffer_append_(\w+)\(buffer, conf->([\w.\[\]]+)(?:, ([\d.]+))?, &ind\);", line)
        if byte:
            key, fmt, scale = byte[1], "B", 1
        elif call:
            key = call[2]
            fmt = {"float32_auto": "f", "float16": "h", "int16": "h", "uint16": "H", "int32": "i", "uint32": "I"}[call[1]]
            scale = float(call[3] or 1)
        else:
            raise ValueError(f"Unrecognized serialization statement: {line}")
        fields[key] = {"offset": offset, "format": fmt, "scale": scale}
        offset += {"B": 1, "h": 2, "H": 2, "i": 4, "I": 4, "f": 4}[fmt]
    sig = int(re.search(rf"#define {name.upper()}_SIGNATURE\s+(\d+)", header)[1])
    layouts[kind] = {"signature": sig, "size": offset, "fields": fields}
out = Path(__file__).resolve().parents[1] / "vesc_workbench" / "fw602-layout.json"
out.write_text(json.dumps({"source_commit": REF, "layouts": layouts}, indent=2) + "\n", encoding="utf-8")
print({k: (v["size"], v["signature"]) for k, v in layouts.items()})
