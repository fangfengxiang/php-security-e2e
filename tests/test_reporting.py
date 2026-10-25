import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('report', ROOT / 'tools/report.py')
report = importlib.util.module_from_spec(spec); spec.loader.exec_module(report)
SAMPLES = ROOT / 'php70/reports/samples'

class ReportingTests(unittest.TestCase):
    def test_recorded_evidence_and_observations(self):
        data = report.normalize(SAMPLES / 'noninstrumented', SAMPLES / 'instrumented')
        self.assertEqual(data['status'], 'PASS')
        self.assertEqual(data['counts'], {'PASS': 94})
        for mode, expected in [('legacy', True), ('hardened', False)]:
            observation = next(x for x in data['observations'] if x['mode'] == mode and x['check'].startswith('script memory_limit OOM'))
            self.assertIs(observation['values']['shutdown_called'], expected)
        legacy = next(t for t in data['timelines'] if t['mode'] == 'legacy' and t['scenario'] == 'multipart')
        hardened = next(t for t in data['timelines'] if t['mode'] == 'hardened' and t['scenario'] == 'multipart')
        self.assertEqual(legacy['events'][5]['event'], 'progress.consume')
        self.assertEqual(hardened['events'][5]['event'], 'progress.blocked')
        self.assertFalse(data['coverage_complete'])

    def test_missing_and_malformed_never_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp); (p / 'summary.json').write_text('{broken')
            data = report.normalize(p, p)
            self.assertFalse(data['pass']); self.assertIn('NOT RUN', data['counts']); self.assertTrue(data['errors'])

    def test_corrupted_nested_schema_remains_reportable(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp); (p / 'summary.json').write_text(json.dumps({'pass': True, 'completed': True, 'modes': []}))
            data = report.normalize(p, p)
            self.assertFalse(data['pass']); self.assertTrue(data['errors'])
            report.render(data, (ROOT / 'templates/report.html').read_text())

    def test_source_mismatch(self):
        data = report.normalize(SAMPLES / 'noninstrumented', SAMPLES / 'instrumented', {'source_commit': 'wrong'})
        self.assertFalse(data['pass']); self.assertTrue(any('mismatch' in e['error'] for e in data['errors']))

    def test_failure_is_not_hidden_by_root_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp); s = json.loads((SAMPLES / 'noninstrumented/summary.json').read_text())
            s['modes']['hardened']['checks'][0]['pass'] = False
            (p / 'summary.json').write_text(json.dumps(s))
            data = report.normalize(p, SAMPLES / 'instrumented')
            self.assertFalse(data['pass']); self.assertGreater(data['counts'].get('FAIL', 0), 0)

    def test_incomplete_trace_and_no_script_injection(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp); s = json.loads((SAMPLES / 'instrumented/summary.json').read_text())
            s['modes']['hardened']['trace']['requests'][1]['events'][0]['sequence'] = 99
            s['modes']['hardened']['trace']['requests'][1]['events'][0]['event'] = '</script><script>alert(1)</script>'
            (p / 'summary.json').write_text(json.dumps(s))
            data = report.normalize(SAMPLES / 'noninstrumented', p)
            self.assertFalse(data['pass']); self.assertIn('INCONCLUSIVE', data['counts'])
            text = report.render(data, (ROOT / 'templates/report.html').read_text())
            self.assertNotIn('</script><script>alert(1)', text)
            self.assertIn('\\u003c/script', text)

    def test_history_keeps_failures_and_previous_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); site = root / 'site'
            data = report.normalize(SAMPLES / 'noninstrumented', SAMPLES / 'instrumented')
            template = (ROOT / 'templates/report.html').read_text()
            for ident, status in [('1', 'PASS'), ('2', 'FAIL')]:
                output = root / ('run' + ident); data['status'] = status
                report.write_report(data, output, template)
                (output / 'manifest.json').write_text('{}')
                subprocess.run([sys.executable, str(ROOT / 'tools/publish_history.py'), '--site', str(site), '--report', str(output), '--run-id', ident, '--attempt', '1'], check=True)
            self.assertEqual(json.loads((site / 'summary.json').read_text())['status'], 'FAIL')
            self.assertTrue((site / 'runs/1-1/index.html').exists())
            self.assertEqual(len(json.loads((site / 'history.json').read_text())), 2)

    def test_read_only_normalization(self):
        p = SAMPLES / 'noninstrumented/summary.json'; before = p.read_bytes()
        report.normalize(SAMPLES / 'noninstrumented', SAMPLES / 'instrumented')
        self.assertEqual(p.read_bytes(), before)

if __name__ == '__main__': unittest.main()
