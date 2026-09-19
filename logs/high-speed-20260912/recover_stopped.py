"""Restore the recorded baseline only after verified standstill; never drive."""
from dataclasses import replace
from pathlib import Path
import sys
import argparse

sys.path.insert(0, r'C:\Users\jando\Desktop\Codex\2026-08-11\e-d\outputs')
from vesc_workbench.bench import Campaign, HardwareBench, load_plan, write_json
from vesc_workbench.wire_config import decode_config

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--output', default='recovery-450rpm')
args = parser.parse_args()
baseline = (root / 'baseline-normalized' / 'mcconf.bin').read_bytes()
decode_config(baseline, 'motor')
plan = replace(load_plan(root / '450rpm.json'), settle_timeout_s=30)
plan.validate()
output = root / args.output
output.mkdir(exist_ok=False)
bench = HardwareBench('COM10')
reason = None
last_sample = None
try:
    bench.snapshot(output / 'before')
    bench.prepare(plan)
    Campaign(bench, plan, output).settle()
    last_sample = bench.sample()
    # Reuse the existing stop/standstill/write/strict-readback recovery path.
    bench.motor = baseline
    bench.modified = True
except (Exception, KeyboardInterrupt) as exc:
    reason = str(exc) or type(exc).__name__
finally:
    cleanup = bench.close()
    result = dict(reason=reason, last_sample=last_sample, cleanup=cleanup,
                  baseline_restored=reason is None and cleanup.get('motor_restored')
                  and not cleanup.get('error'))
    write_json(output / 'result.json', result)
    print(result)
raise SystemExit(0 if result['baseline_restored'] else 2)
