from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from vesc_workbench.bench import BenchPlan, BenchStop, Campaign, EncoderMotion, SimulatedBench, guard, load_plan
from vesc_workbench.qualification import speed_steps, startup_coverage


class QualificationTests(TestCase):
    def test_batched_encoder_arrivals_do_not_inflate_speed(self):
        motion = EncoderMotion(2, 1)
        # True speed 150 mechanical RPM; four 5-ms samples per USB burst.
        for n in range(1, 31):
            end = n * .02
            samples = [(end + i * .000001, ((end - .015 + i*.005)*900) % 360)
                       for i in range(4)]
            motion.update(samples, batched=True)
        self.assertAlmostEqual(motion.speed, 300, places=3)
        self.assertAlmostEqual(motion.turns, (.6 - .005)*2.5, places=6)

    def samples(self, seconds=10, target=300, actual=300):
        return [dict(t=n/10, target_erpm=target, encoder_erpm=actual)
                for n in range(int(seconds*10) + 1)]

    def test_steady_speed_passes(self):
        row = speed_steps(self.samples())[0]
        self.assertTrue(row['qualified'])
        self.assertEqual(row['rmse_erpm'], 0)

    def test_short_test_is_not_qualified(self):
        self.assertFalse(speed_steps(self.samples(2))[0]['qualified'])

    def test_overshoot_drift_and_dropouts_fail(self):
        overshoot = self.samples(actual=345)
        drift = self.samples()
        for row in drift:
            row['encoder_erpm'] += 8*(row['t']-7.5)
        dropout = self.samples()
        dropout[-10]['encoder_erpm'] = 0
        for samples in (overshoot, drift, dropout):
            self.assertFalse(speed_steps(samples)[0]['qualified'])

    def test_repeated_targets_are_separate_steps(self):
        samples = []
        for n, target in enumerate((60, 300, 60)):
            for row in self.samples(target=target, actual=target):
                row['t'] += n*10.1
                samples.append(row)
        self.assertEqual([r['target_erpm'] for r in speed_steps(samples)], [60, 300, 60])

    def test_startup_requires_full_coverage_same_candidate(self):
        starts = [dict(stage='startup', ok=True, startup_s=.5, start_angle=15+30*n,
                       changes={'offset': 90}) for n in range(12) for _ in range(3)]
        self.assertTrue(startup_coverage(starts)['qualified'])
        self.assertFalse(startup_coverage(starts[:-1])['qualified'])
        self.assertFalse(startup_coverage(starts[:3]*12)['qualified'])
        self.assertFalse(startup_coverage([*starts, {**starts[0], 'ok': False}])['qualified'])
        starts[-1]['changes'] = {'offset': 0}
        self.assertFalse(startup_coverage(starts)['qualified'])

    def test_speed_motion_does_not_count_as_start(self):
        self.assertFalse(startup_coverage([dict(stage='speed', ok=True)])['qualified'])

    def test_trial_duration_limits(self):
        for plan in (replace(BenchPlan(), trial_s=61),
                     replace(BenchPlan(), speed_hold_s=31),
                     replace(BenchPlan(), qualify_speed=True),
                     replace(BenchPlan(), cooldown_s=16)):
            with self.assertRaises(ValueError):
                plan.validate()

    def test_prepared_plans_and_temperature_gate(self):
        root = Path(__file__).resolve().parents[1]
        short = load_plan(root/'config/synrm-start-12a-5s.json')
        long = load_plan(root/'config/synrm-speed-60s-temperature-required.json')
        self.assertEqual(short.phase_limit_a, 15)
        b = SimulatedBench()
        b.prepare(long)
        with self.assertRaises(BenchStop):
            guard({**b.sample(), 'temp_motor_c': -50.6}, long)
        with self.assertRaises(ValueError):
            replace(long, allow_missing_motor_temp=True).validate()

    def test_missing_temperature_prevents_writes_and_motion(self):
        class NoTemperature(SimulatedBench):
            applied = False
            def apply(self, changes):
                self.applied = True
            def sample(self):
                return {**super().sample(), 'temp_motor_c': -50.6}
        with TemporaryDirectory() as tmp:
            b = NoTemperature()
            p = load_plan(Path(__file__).resolve().parents[1]/'config/synrm-speed-60s-temperature-required.json')
            c = Campaign(b, p, Path(tmp)/'run', True)
            c.run()
            self.assertEqual(c.state, 'stopped')
            self.assertFalse(b.applied)
            self.assertEqual(b.command, 0)

    def test_speed_duration_never_ignores_trial_limit(self):
        with TemporaryDirectory() as tmp:
            b = SimulatedBench()
            p = replace(BenchPlan(), cooldown_s=.5, trial_s=1, ramp_s=.2,
                        trial_i2t=200, trial_energy_j=100, total_energy_j=200)
            b.prepare(p)
            c = Campaign(b, p, Path(tmp), True)
            row = c.trial('speed', {'foc_mtpa_mode': 1}, speed=True)
            self.assertLessEqual(row['duration_s'], 1 + p.sample_s)
            self.assertFalse(row['speed_qualified'])

    def test_long_completed_run_with_speed_error_is_rejected(self):
        with TemporaryDirectory() as tmp:
            b = SimulatedBench()
            p = replace(BenchPlan(), qualify_speed=True, cooldown_s=.5,
                        speed_targets=(300,), speed_hold_s=10, trial_s=10,
                        trial_i2t=1000, trial_energy_j=1000, total_energy_j=2000)
            b.prepare(p)
            c = Campaign(b, p, Path(tmp), True)
            row = c.trial('speed', {'foc_mtpa_mode': 1}, speed=True)
            self.assertFalse(row['ok'])
            self.assertEqual(row['status'], 'speed_unqualified')
            self.assertGreaterEqual(row['duration_s'], 10)
            self.assertTrue(b.stopped)
