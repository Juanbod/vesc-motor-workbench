from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from test_locked_probe import app, motor
from vesc_workbench import field_alignment as fa
from vesc_workbench.fixture import FixtureInterlock, require_free
from vesc_workbench.locked_rotor import angular_delta, axial_delta
from vesc_workbench.uart import VescFirmwareVersion, VescValues
from vesc_workbench.wire_config import patch_config


def rows(angle=359.9, current=.5):
    return [dict(t=i*.02, position_deg=angle, id_a=current, iq_a=0,
                 current_motor_a=current, current_in_a=.01, duty=.005,
                 erpm=9999, v_in=25, temp_mos_c=25, temp_motor_c=-50, fault_code=0)
            for i in range(16)]


class FakeClient:
    def __init__(self, clock, *, stuck=False, fail_sample=False, mismatch=False, done=True, settle_time=.2):
        self.clock = clock
        self.serial = SimpleNamespace(timeout=.15)
        self.motor = patch_config(motor(), 'motor', dict(foc_encoder_ratio=2,
            l_current_max_scale=1, l_current_min_scale=1))
        self.app = app()
        self.prints = []
        self.pid_position = 15.5
        self.start = None
        self.duration = .8
        self.start_angle = self.target = self.pid_position
        self.current = .5
        self.completed = True
        self.stuck, self.fail_sample, self.mismatch, self.done = stuck, fail_sample, mismatch, done
        self.settle_time = settle_time
        self.zero_count = self.pulses = self.writes = 0
        self.payloads = []

    def fw_version(self):
        return VescFirmwareVersion(6, 2, 'MKSESC_84_100_HP')

    def get_raw_config(self, kind):
        if kind == 'motor' and self.mismatch and self.writes == 1:
            return patch_config(self.motor, 'motor', dict(l_current_max=4))
        return self.motor if kind == 'motor' else self.app

    def set_raw_config(self, kind, data):
        self.writes += 1
        self.motor = data

    def read_response(self, command):
        return bytes([command])

    def set_app_config_temporary(self, data):
        self.app = data

    def set_current(self, current):
        if current != 0:
            raise AssertionError('Only direct zero current allowed')
        self.zero_count += 1

    def send_payload(self, payload):
        self.payloads.append(payload)
        if not payload.startswith(b'\x14rotor_lock_openloop '):
            raise AssertionError('Unexpected command')
        _, current, duration, phase = payload[1:].decode().split()
        self.current, self.duration = float(current), float(duration)
        if self.duration <= 0:
            raise AssertionError('Unbounded pulse')
        self.pulses += 1
        self.start = self.clock[0]
        self.start_angle = self.pid_position
        self.target = self.start_angle + axial_delta(float(phase)+90+351, 2*self.start_angle)/2
        self.completed = False

    def get_values(self):
        self.clock[0] += .002
        active = False
        if self.start is not None:
            age = self.clock[0]-self.start
            if self.fail_sample and age > .1:
                self.fail_sample = False
                raise TimeoutError('injected telemetry loss')
            if not self.stuck:
                self.pid_position = (self.start_angle + (self.target-self.start_angle)*min(age/self.settle_time, 1))%360
            active = age < self.duration
            if not active and not self.completed:
                if self.done:
                    self.prints.append(dict(t=self.clock[0], text='Done'))
                self.completed = True
        return VescValues(temp_mos_c=25, temp_motor_c=-50, current_motor_a=self.current if active else 0,
                          current_in_a=.01 if active else 0, id_a=self.current if active else 0,
                          iq_a=0, duty=.005 if active else 0, erpm=9876,
                          v_in=25, fault_code=0)


class AlignmentTests(unittest.TestCase):
    def test_plan_bounded(self):
        for mode in ('pilot', 'sweep'):
            p = fa.plan(mode)
            self.assertLessEqual(p['commanded_on_time_s'], 21)
            self.assertFalse(p['offset_auto_apply'])
        self.assertEqual(len(fa.plan('sweep')['steps']), 26)
        for bad in (0, 3, 70, float('nan')):
            with self.assertRaises(ValueError):
                fa.plan(current=bad)

    def test_locked_and_unknown_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'fixture.json'
            with patch('vesc_workbench.fixture.FIXTURE_PATH', path):
                for content in ('{}', '{', json.dumps(dict(schema='vesc-fixture-v1', rotor='locked', confirmed_by_user=True))):
                    path.write_text(content)
                    with self.assertRaises(FixtureInterlock):
                        require_free()

    def test_wrap_settling_and_observer_not_used(self):
        r = rows()
        for i, row in enumerate(r):
            row['position_deg'] = (359.98 + .03*(i%2))%360
        self.assertLess(abs(angular_delta(fa.settled_position(r, .5), 0)), .03)

    def test_current_and_settling_required(self):
        for key, value in [('id_a', 0), ('iq_a', .5), ('position_deg', 20), ('t', 1.)]:
            r = rows()
            r[-1][key] = value
            with self.assertRaises(ValueError):
                fa.settled_position(r, .5)

    def test_guards(self):
        for key, value in [('current_motor_a', 3), ('current_in_a', 2), ('duty', .2),
                           ('temp_mos_c', 60), ('fault_code', 1), ('v_in', 35), ('id_a', float('nan'))]:
            r = rows()[0]
            r[key] = value
            with self.assertRaises(ValueError):
                fa.check_motion(r)

    def test_synthetic_full_turn_tracks_unwrapped(self):
        spec = fa.plan('sweep')
        # Select successive physical equilibria, not arbitrary modulo-90 branches.
        steps = []
        previous = 15.5
        for s in spec['steps']:
            previous += axial_delta(s['phase_deg']+90+351, 2*previous)/2
            steps.append(dict(s, settled=True, completed=True, encoder_deg=previous%360))
        a = fa.analyze(steps, spec)
        self.assertIsNotNone(a['candidate'])
        self.assertAlmostEqual(a['candidate']['offset_candidates_deg'][1], 351)
        self.assertFalse(a['global_calibration_validated'])
        steps[5]['encoder_deg'] = steps[4]['encoder_deg']
        with self.assertRaises(ValueError):
            fa.analyze(steps, spec)

    def exercise(self, spec=None, **kwargs):
        with tempfile.TemporaryDirectory() as d, ExitStack() as stack:
            clock = [1.]
            stack.enter_context(patch.object(fa, 'monotonic', lambda: clock[0]))
            stack.enter_context(patch.object(fa, 'sleep', lambda t: clock.__setitem__(0, clock[0]+t)))
            stack.enter_context(patch.object(fa, 'require_free'))
            stack.enter_context(patch.object(fa, 'terminal_expect'))
            client = FakeClient(clock, **kwargs)
            baseline = Path(d)/'baseline.bin'
            baseline.write_bytes(client.motor)
            original = client.motor
            result = fa.run(client, Path(d)/'run', baseline, spec or fa.plan())
            self.assertEqual(json.loads((Path(d)/'run/result.json').read_text())['ok'], result['ok'])
            self.assertEqual(client.motor, original)
            self.assertTrue(result['zero_current_verified'])
            self.assertTrue(result['baseline_restored'])
            self.assertGreater(client.zero_count, 50)
            return result, client

    def test_pilot_physical_success(self):
        r, c = self.exercise()
        self.assertTrue(r['ok'], r['errors'])
        self.assertTrue(r['physical_motion_verified'])
        self.assertEqual(c.pulses, 1)
        self.assertEqual(r['analysis']['status'], 'pilot_only')
        fa.validate_pilot(r, fa.plan('sweep'), r['baseline_sha256'])
        with self.assertRaises(ValueError):
            fa.validate_pilot(r, fa.plan('sweep', current=1), r['baseline_sha256'])

    def test_stuck_is_not_success(self):
        r, c = self.exercise(stuck=True)
        self.assertFalse(r['ok'])
        self.assertFalse(r['physical_motion_verified'])
        self.assertEqual(c.pulses, 1)

    def test_motion_without_settling_is_not_sweep_approval(self):
        r, c = self.exercise(settle_time=1.1)
        self.assertFalse(r['ok'])
        self.assertTrue(r['physical_motion_verified'])
        self.assertFalse(r['steps'][0]['settled'])
        self.assertGreater(r['steps'][0]['max_powered_displacement_deg'], 1)
        with self.assertRaises(ValueError):
            fa.validate_pilot(r, fa.plan('sweep'), r['baseline_sha256'])

    def test_longer_hold_and_matching_pilot_duration(self):
        r, c = self.exercise(spec=fa.plan(dwell_s=2), settle_time=1.1)
        self.assertTrue(r['ok'], r['errors'])
        self.assertIn(b'2.000', c.payloads[0])
        fa.validate_pilot(r, fa.plan('sweep', dwell_s=2), r['baseline_sha256'])
        with self.assertRaises(ValueError):
            fa.validate_pilot(r, fa.plan('sweep'), r['baseline_sha256'])
        for bad in (0, -1, 3, 60, float('nan')):
            with self.assertRaises(ValueError):
                fa.plan(dwell_s=bad)

    def test_coast_down_waits_without_new_excitation(self):
        r, c = self.exercise(settle_time=3)
        self.assertFalse(r['ok'])
        self.assertTrue(r['physical_motion_verified'])
        self.assertTrue(r['baseline_restored'])
        self.assertEqual(c.pulses, 1)

    def test_four_second_hold_is_finite(self):
        r, c = self.exercise(spec=fa.plan(dwell_s=4), settle_time=2.5)
        self.assertTrue(r['ok'], r['errors'])
        self.assertEqual(c.duration, 4)
        fa.validate_pilot(r, fa.plan('sweep', dwell_s=4), r['baseline_sha256'])

    def test_loss_of_telemetry_stops_and_restores(self):
        r, c = self.exercise(fail_sample=True)
        self.assertFalse(r['ok'])
        self.assertEqual(c.pulses, 1)
        self.assertIn('injected telemetry loss', r['errors'][0])

    def test_config_mismatch_never_excites(self):
        r, c = self.exercise(mismatch=True)
        self.assertFalse(r['ok'])
        self.assertEqual(c.pulses, 0)

    def test_no_completion_stops(self):
        r, c = self.exercise(done=False)
        self.assertFalse(r['ok'])
        self.assertEqual(c.pulses, 1)

    def test_full_sweep_after_pilot(self):
        with tempfile.TemporaryDirectory() as d, ExitStack() as stack:
            clock = [1.]
            stack.enter_context(patch.object(fa, 'monotonic', lambda: clock[0]))
            stack.enter_context(patch.object(fa, 'sleep', lambda t: clock.__setitem__(0, clock[0]+t)))
            stack.enter_context(patch.object(fa, 'require_free'))
            stack.enter_context(patch.object(fa, 'terminal_expect'))
            c = FakeClient(clock)
            baseline = Path(d)/'baseline.bin'
            baseline.write_bytes(c.motor)
            p = fa.run(c, Path(d)/'pilot', baseline, fa.plan())
            self.assertTrue(p['ok'], p['errors'])
            sweep = fa.run(c, Path(d)/'sweep', baseline, fa.plan('sweep'), p)
            self.assertTrue(sweep['ok'], sweep['errors'])
            self.assertEqual(c.pulses, 27)
            self.assertEqual(len(sweep['steps']), 26)
            self.assertAlmostEqual(sweep['analysis']['candidate']['offset_candidates_deg'][1], 351)
            self.assertFalse(sweep['offset_applied'])
            c.pulses = 0
            rejected = fa.run(c, Path(d)/'missing-pilot', baseline, fa.plan('sweep'))
            self.assertFalse(rejected['ok'])
            self.assertEqual(c.pulses, 0)

    def test_hysteresis_rejects_candidate(self):
        spec = fa.plan('sweep')
        previous = 15.5
        steps = []
        for s in spec['steps']:
            previous += axial_delta(s['phase_deg']+90+351, 2*previous)/2
            measured = previous + (2 if s['direction'] == 'reverse' else 0)
            steps.append(dict(s, settled=True, completed=True, encoder_deg=measured%360))
        result = fa.analyze(steps, spec)
        self.assertIsNone(result['candidate'])
        self.assertAlmostEqual(result['hysteresis_electrical_deg'], 4)

    def test_fixture_refusal_before_any_io(self):
        with patch.object(fa, 'require_free', side_effect=FixtureInterlock('locked')):
            with self.assertRaises(FixtureInterlock):
                fa.run(None, 'not-created', 'not-read', fa.plan())


if __name__ == '__main__':
    unittest.main()
