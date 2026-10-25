"""Negative evidence controls for the CLI cgroup gate."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('cli_pressure', Path(__file__).resolve().parents[1] / 'php70/harness/cli-memory-pressure.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CliMemoryTests(unittest.TestCase):
    def test_requires_kernel_victim_and_callback_evidence(self):
        before = {'memory.max': 64 * 1024 * 1024, 'memory.swap.max': 0, 'memory.events': {'oom_kill': 0}}
        valid = dict(before=before, after=copy.deepcopy(before), size=64 * 1024 * 1024,
                     returncode=-9, stdout='bounded pressure started\n', shutdown=False)
        valid['after']['memory.events']['oom_kill'] = 1
        self.assertTrue(all(cli.checks(**valid).values()))
        for variant in ('no-kernel-event', 'exit-137-only', 'wrong-signal', 'shutdown', 'completed-loop', 'wrong-limit', 'swap', 'not-started'):
            value = copy.deepcopy(valid)
            if variant == 'no-kernel-event': value['after']['memory.events']['oom_kill'] = 0
            if variant == 'exit-137-only': value['returncode'] = 137
            if variant == 'wrong-signal': value['returncode'] = -15
            if variant == 'shutdown': value['shutdown'] = True
            if variant == 'completed-loop': value['stdout'] += 'ALLOCATION_BOUND_REACHED'
            if variant == 'wrong-limit': value['after']['memory.max'] *= 2
            if variant == 'swap': value['before']['memory.swap.max'] = 1
            if variant == 'not-started': value['stdout'] = ''
            with self.subTest(variant=variant):
                self.assertFalse(all(cli.checks(**value).values()))


if __name__ == '__main__':
    unittest.main()
