#!/usr/bin/env python3
"""Recheck an existing run with the current harness; never rebuild or overwrite artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
a = parser.parse_args()
run = a.run.resolve()
previous = json.loads((run / 'summary.json').read_text())
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=False)
harness = out / 'harness'
shutil.copytree(Path(__file__).resolve().parent / 'harness', harness)
result = {'report_mode': 'noninstrumented', 'core_source_instrumented': False, 'native_allocator_checks_load_test_extension': True, 'pass': False, 'completed': False, 'coverage_complete': False,
          'source_commit': previous['source_commit'], 'baseline_commit': previous['baseline_commit'],
          'image_id': previous['image_id'], 'reused_builds': str(run), 'limits': previous['limits'],
          'harness_sha256': {str(p.relative_to(harness)): hashlib.sha256(p.read_bytes()).hexdigest() for p in harness.rglob('*') if p.is_file()}, 'modes': {}}
try:
    for mode in ('baseline', 'legacy', 'hardened'):
        build = run / mode
        # Build's version guard/log must be present, never accept arbitrary host installations.
        if not (build / 'logs/version.txt').read_text().startswith('PHP 7.0.33'):
            raise RuntimeError(mode + ': missing successful branch-build version evidence')
        command = ['docker', 'run', '--rm', '--network', 'none',
                   '-v', str(build) + ':/work:ro', '-v', str(harness) + ':/harness:ro',
                   '-v', str(out) + ':/evidence', '--entrypoint', 'sh', result['image_id']]
        def invoke(script, name):
            with (out / (mode + '-' + name + '.log')).open('wb') as log:
                subprocess.run(command + ['-ec', script], stdout=log, stderr=subprocess.STDOUT, check=True)
        if mode != 'baseline':
            invoke('python3 /harness/native-invariants.py --php /work/install/bin/php --module /work/probe/modules/security_probe.so --output /evidence/' + mode + '-native.json' + (' --legacy' if mode == 'legacy' else ''), 'native')
        invoke('python3 /harness/fpm-invariants.py --fpm /work/install/sbin/php-fpm --output /evidence/' + mode + '-fpm.json' + (' --expect-baseline' if mode != 'hardened' else ''), 'fpm')
        data = json.loads((out / (mode + '-fpm.json')).read_text())
        if not data.get('pass') or not data.get('completed'):
            raise RuntimeError(mode + ': FPM report incomplete')
        result['modes'][mode] = data
    def signature(mode):
        data = next(c for c in result['modes'][mode]['checks'] if c['check'] == 'ordinary fatal cleanup and safe worker reuse')
        return {k: data[k] for k in ('shutdown_called', 'destructor_called')}
    for mode in ('legacy', 'hardened'):
        if signature(mode) != signature('baseline'):
            raise RuntimeError(mode + ': fatal differs from baseline')
    result.update({'pass': True, 'completed': True})
except (Exception, KeyboardInterrupt) as error:
    result['error'] = str(error)
    print(result['error'], file=sys.stderr)
finally:
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
sys.exit(0 if result['pass'] else 1)
