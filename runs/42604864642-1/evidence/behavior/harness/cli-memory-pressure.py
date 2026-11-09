#!/usr/bin/env python3
"""Keep the cgroup alive while recording the bounded PHP CLI child's OOM evidence."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time


def snapshot():
    root = Path('/sys/fs/cgroup')
    return {
        'memory.max': int((root / 'memory.max').read_text()),
        'memory.swap.max': int((root / 'memory.swap.max').read_text()),
        'memory.events': dict((k, int(v)) for k, v in
                              (line.split() for line in (root / 'memory.events').read_text().splitlines())),
    }


def checks(before, after, size, returncode, stdout, shutdown):
    return {
        'exact cgroup memory cap': before['memory.max'] == after['memory.max'] == size,
        'swap disabled': before['memory.swap.max'] == after['memory.swap.max'] == 0,
        'kernel OOM kill counted': after['memory.events']['oom_kill'] > before['memory.events']['oom_kill'],
        'PHP CLI child killed by SIGKILL': returncode == -signal.SIGKILL,
        'bounded pressure started': 'bounded pressure started' in stdout,
        'allocation bound not reached': 'ALLOCATION_BOUND_REACHED' not in stdout,
        'no PHP shutdown callback': not shutdown,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--php', required=True)
    p.add_argument('--script', required=True)
    p.add_argument('--container-bytes', type=int, required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    output = Path(a.output)
    report = {'pass': False, 'completed': False, 'checks': {}, 'allocation_bound_mib': 512}
    child = None
    started = time.monotonic()
    try:
        version = subprocess.check_output([a.php, '-n', '-r', 'echo PHP_VERSION;'], universal_newlines=True)
        if version != '7.0.33':
            raise RuntimeError('Expected branch-built PHP 7.0.33, got ' + version)
        report['php_version'] = version
        report['before'] = snapshot()
        # Prefer the allocating child as victim; retain the observer so the
        # cgroup and its counters still exist after the PHP process exits.
        def prefer_child():
            Path('/proc/self/oom_score_adj').write_text('1000')
        child = subprocess.Popen([a.php, '-n', '-d', 'memory_limit=-1', a.script],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 preexec_fn=prefer_child)
        report['php_pid'] = child.pid
        stdout, stderr = child.communicate(timeout=60)
        report.update(returncode=child.returncode, stdout=stdout.decode(errors='replace'),
                      stderr=stderr.decode(errors='replace'), after=snapshot())
        report['checks'] = checks(report['before'], report['after'], a.container_bytes,
                                  child.returncode, report['stdout'],
                                  (output.parent / 'cli-shutdown-marker').exists())
        report['completed'] = True
        report['pass'] = all(report['checks'].values())
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate()
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'pass': report['pass']}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
