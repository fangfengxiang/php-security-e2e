#!/usr/bin/env python3
"""Build the same committed PHP tree in isolated comparison modes and retain evidence."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


def execute(command, log, **kwargs):
    with log.open('wb') as stream:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2] / 'php-src')
    parser.add_argument('--ref', default='HEAD', help='Committed branch revision; dirty files are refused')
    parser.add_argument('--baseline', default='bf574c2b67a1f786e36cf679f41b758b973a82c4')
    parser.add_argument('--output', type=Path, required=True, help='New directory only')
    parser.add_argument('--image', default='php-cve-e2e:php70')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--reuse-image', action='store_true')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    source = args.source.resolve()
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain']).strip():
        parser.error('Source tree is dirty; commit the intended changes before archiving')
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', args.ref + '^{commit}'], text=True).strip()
    baseline = subprocess.check_output(['git', '-C', str(source), 'rev-parse', args.baseline + '^{commit}'], text=True).strip()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    harness = output / 'harness'
    shutil.copytree(Path(__file__).resolve().parent / 'harness', harness)
    summary = {'report_mode': 'noninstrumented', 'core_source_instrumented': False, 'native_allocator_checks_load_test_extension': True, 'pass': False, 'completed': False, 'source_commit': revision,
               'baseline_commit': baseline, 'started_utc': datetime.now(timezone.utc).isoformat(),
               'modes': {}, 'coverage_complete': False, 'harness_sha256': {str(p.relative_to(harness)): hashlib.sha256(p.read_bytes()).hexdigest() for p in harness.rglob('*') if p.is_file()}, 'limits': ['Pre-RINIT session consumer ordering requires native instrumentation/source review; session-key absence alone is insufficient.',
               'Startup OOM precedes user script registration; user shutdown/destructor absence there is not proof of _exit.',
               'HTTP globals/handler checks cover observable request state, not all internal lifecycle fields.']}
    try:
        for name, ref in [('source', revision), ('baseline', baseline)]:
            execute(['git', '-C', str(source), 'archive', '--format=tar', '--output=' + str(output / (name + '.tar')), ref], output / (name + '-archive.log'))
            summary[name + '_sha256'] = hashlib.sha256((output / (name + '.tar')).read_bytes()).hexdigest()
        if not args.reuse_image:
            print('Building toolchain image', flush=True)
            execute(['docker', 'build', '-t', args.image, str(harness)], output / 'image-build.log')
        summary['image_id'] = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], text=True).strip()
        for mode, build_mode in [('baseline', 'baseline'), ('legacy', 'legacy'), ('hardened', 'debug')]:
            folder = output / mode
            folder.mkdir()
            summary['modes'][mode] = {'pass': False}
            archive = output / ('baseline.tar' if mode == 'baseline' else 'source.tar')
            command = ['docker', 'run', '--rm', '--network', 'none',
                       '--security-opt=no-new-privileges', '-e', 'BUILD_JOBS=' + str(args.jobs),
                       '-e', 'PYTHONOPTIMIZE=', '-v', str(archive) + ':/input/source.tar:ro',
                       '-v', str(harness) + ':/harness:ro', '-v', str(folder) + ':/work',
                       '--entrypoint', 'sh', args.image]
            build_command = [x for x in command]
            print('Building ' + mode + ' from ' + (baseline if mode == 'baseline' else revision), flush=True)
            execute(build_command + ['/harness/build.sh', build_mode], folder / 'build.log')
            if mode != 'baseline':
                execute(command + ['/harness/build-probe.sh'], folder / 'probe-build.log')
                execute(command + ['-ec', 'python3 /harness/native-invariants.py --php /work/install/bin/php --module /work/probe/modules/security_probe.so --output /work/native.json' + (' --legacy' if mode == 'legacy' else '')], folder / 'native-run.log')
            # uid 65534 owns its transient socket and sessions; installation stays read-only to it.
            test_command = command.copy()
            test_command[test_command.index('--entrypoint'):test_command.index('--entrypoint')] = ['--user', '65534:65534', '--cap-drop=ALL']
            # Evidence path is prepared by root; only the logs directory is writable by test uid.
            execute(command + ['-ec', 'mkdir -p /work/evidence; chmod 777 /work/evidence'], folder / 'prepare.log')
            execute(test_command + ['-ec', 'python3 /harness/fpm-invariants.py --fpm /work/install/sbin/php-fpm --output /work/evidence/fpm.json' + (' --expect-baseline' if mode != 'hardened' else '')], folder / 'fpm-run.log')
            report = json.loads((folder / 'evidence/fpm.json').read_text())
            if not report.get('completed') or not report.get('pass'):
                raise RuntimeError(mode + ': incomplete FPM report')
            native = None
            if mode != 'baseline':
                native = json.loads((folder / 'native.json').read_text())
                if not native.get('completed') or not native.get('pass'):
                    raise RuntimeError(mode + ': incomplete native report')
            summary['modes'][mode] = {'pass': True, 'fpm': report, 'native': native}
        def fatal_signature(mode):
            checks = summary['modes'][mode]['fpm']['checks']
            check = next(c for c in checks if c['check'] == 'ordinary fatal cleanup and safe worker reuse')
            return {k: check[k] for k in ('shutdown_called', 'destructor_called')}
        reference = fatal_signature('baseline')
        for mode in ('legacy', 'hardened'):
            if fatal_signature(mode) != reference:
                raise RuntimeError(mode + ': ordinary fatal semantics differ from fixed baseline')
        summary['fatal_baseline_signature'] = reference
        summary['coverage_complete'] = False
        summary['completed'] = True
        summary['pass'] = True
    except (Exception, KeyboardInterrupt) as error:
        summary['error'] = type(error).__name__ + ': ' + str(error)
        print(summary['error'], file=sys.stderr)
    finally:
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 0 if summary['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
