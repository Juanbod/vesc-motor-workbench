"""Build an offline draft; never opens the motor controller."""
import argparse
import json
from pathlib import Path
from vesc_workbench.motor_passport import build_passport, render_markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='config/motor-passport.json')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root/args.manifest).read_text(encoding='utf-8'))
    data = build_passport(manifest, root)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    (output/'motor-passport-draft.json').write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (output/'motor-passport-draft.md').write_text(render_markdown(data), encoding='utf-8')
    print(json.dumps(dict(output=str(output.resolve()), accepted=len(data['verified_runs']),
                          excluded=len(data['excluded_runs']), status=data['status']), ensure_ascii=False))


if __name__ == '__main__':
    main()
