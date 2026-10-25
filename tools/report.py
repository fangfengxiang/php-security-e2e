#!/usr/bin/env python3
"""Read real evidence without modifying it; emit offline HTML, JSON, Markdown and JUnit."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import xml.etree.ElementTree as ET

MODES = ('baseline', 'legacy', 'hardened')


def normalize(e2e, trace, metadata=None):
    errors, sources, cases, observations, timelines = [], {}, [], [], []
    def read(path, required=False):
        if not path.is_file():
            if required: errors.append({'file': str(path), 'error': 'NOT RUN: evidence missing'})
            return None
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict): raise ValueError('Expected JSON object')
            sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            return value
        except (ValueError, OSError) as exc:
            errors.append({'file': str(path), 'error': str(exc)})
            return None
    behavior = read(e2e / 'summary.json', True) or {}
    instrument = read(trace / 'summary.json', True) or {}
    for label, run in [('behavior', behavior), ('instrumented', instrument)]:
        if not isinstance(run.get('modes', {}), dict):
            errors.append({'file': label + '/summary.json', 'error': 'Invalid modes mapping'})
            run['modes'] = {}
    def add_checks(report, mode, suite, origin):
        if not isinstance(report, dict): return
        checks = report.get('checks', [])
        if not isinstance(checks, list):
            errors.append({'file': origin, 'error': 'Invalid checks list'}); return
        for record in checks:
            if not isinstance(record, dict) or not isinstance(record.get('check'), str):
                errors.append({'file': origin, 'error': 'Malformed assertion'}); continue
            status = 'SKIP' if record.get('skip') else ('PASS' if record.get('pass') is True else 'FAIL' if record.get('pass') is False else 'INCONCLUSIVE')
            cases.append({'mode': mode, 'suite': suite, 'name': record['check'], 'status': status, 'evidence': origin, 'raw': record})
            if suite == 'behavior/fpm':
                observations.append({'mode': mode, 'check': record['check'], 'evidence': origin,
                    'values': {k: record[k] for k in ('has_progress', 'before_pid', 'after_pid', 'shutdown_called', 'destructor_called', 'master_alive') if k in record},
                    'response_ended': (record.get('response') if isinstance(record.get('response'), dict) else {}).get('ended')})
        if report.get('error') or report.get('failure') or report.get('completed') is False or report.get('pass') is False:
            cases.append({'mode': mode, 'suite': suite, 'name': 'Runner completion', 'status': 'FAIL' if report.get('pass') is False else 'ERROR', 'evidence': origin, 'raw': report})
    for mode in MODES:
        entry = behavior.get('modes', {}).get(mode, {})
        if not isinstance(entry, dict):
            errors.append({'file': 'behavior/' + mode, 'error': 'Invalid mode entry'}); entry = {}
        fpm = entry.get('fpm') or (entry if 'checks' in entry else None)
        fpm_path = e2e / mode / 'evidence/fpm.json'
        if not fpm: fpm = read(fpm_path) or read(e2e / (mode + '-fpm.json'))
        add_checks(fpm, mode, 'behavior/fpm', str(fpm_path if fpm_path.exists() else e2e / 'summary.json'))
        native_path = e2e / mode / 'native.json'
        native = entry.get('native') or read(native_path) or read(e2e / (mode + '-native.json'))
        add_checks(native, mode, 'behavior/native', str(native_path if native_path.exists() else e2e / (mode + '-native.json')))
    for mode in ('legacy', 'hardened'):
        entry = instrument.get('modes', {}).get(mode, {})
        if not isinstance(entry, dict):
            errors.append({'file': 'instrumented/' + mode, 'error': 'Invalid mode entry'}); entry = {}
        tr_path = trace / mode / 'trace.json'
        tr = entry.get('trace') or read(tr_path)
        if tr is not None and not isinstance(tr, dict):
            errors.append({'file': str(tr_path), 'error': 'Invalid trace object'}); tr = None
        regression = entry.get('regression') or read(trace / mode / 'fpm.json')
        add_checks(regression, mode, 'instrumented/fpm', str(trace / mode / 'fpm.json'))
        requests = tr.get('requests', []) if isinstance(tr, dict) else []
        if not isinstance(requests, list):
            errors.append({'file': str(tr_path), 'error': 'Invalid trace requests'}); requests = []
        for request in requests:
            if not isinstance(request, dict):
                errors.append({'file': str(tr_path), 'error': 'Invalid request'}); continue
            events = request.get('events', [])
            valid = isinstance(events, list) and bool(events) and all(isinstance(e, dict) and isinstance(e.get('sequence'), int) and isinstance(e.get('event'), str) and e.get('rinit') in (0, 1) for e in events)
            valid = valid and [e['sequence'] for e in events] == list(range(1, len(events) + 1))
            cases.append({'mode': mode, 'suite': 'instrumented/trace', 'name': request.get('scenario', 'unnamed'),
                'status': ('PASS' if request.get('pass') is True else 'FAIL') if valid else 'INCONCLUSIVE', 'evidence': str(tr_path), 'raw': request})
            timelines.append({'mode': mode, 'scenario': request.get('scenario'), 'pid': request.get('pid'), 'ordinal': request.get('ordinal'), 'events': events if valid else [], 'sequence_valid': valid, 'evidence': str(tr_path)})
        if tr and (tr.get('pass') is False or tr.get('completed') is False):
            cases.append({'mode': mode, 'suite': 'instrumented/trace', 'name': 'Runner completion', 'status': 'ERROR', 'evidence': str(tr_path), 'raw': tr})
    # Required plans are explicit; missing or partial runners never become a green cell.
    for mode in MODES:
        required = [('behavior/fpm', 12)] + ([('behavior/native', 13), ('instrumented/fpm', 12), ('instrumented/trace', 4)] if mode != 'baseline' else [])
        for suite, expected in required:
            count = len([c for c in cases if c['mode'] == mode and c['suite'] == suite and c['name'] != 'Runner completion'])
            if count < expected:
                cases.append({'mode': mode, 'suite': suite, 'name': 'Required plan completion', 'status': 'NOT RUN', 'evidence': '', 'raw': {'observed': count, 'minimum_expected': expected}})
    identities = {key: {'behavior': behavior.get(key), 'instrumented': instrument.get(key)} for key in ('source_commit', 'baseline_commit', 'image_id')}
    if behavior.get('source_commit') and instrument.get('source_commit') and behavior['source_commit'] != instrument['source_commit']:
        errors.append({'file': 'source identity', 'error': 'Behavior/trace source commit mismatch'})
    if metadata and metadata.get('source_commit') and behavior.get('source_commit') and metadata['source_commit'] != behavior['source_commit']:
        errors.append({'file': 'source identity', 'error': 'CI source commit mismatch'})
    for name, run in [('behavior', behavior), ('instrumented', instrument)]:
        if run.get('pass') is not True or run.get('completed') is not True:
            errors.append({'file': name + '/summary.json', 'error': run.get('error', 'INCOMPLETE: runner not completed and passing')})
    counts = dict(Counter(c['status'] for c in cases))
    status = 'PASS' if not errors and all(c['status'] in ('PASS', 'SKIP') for c in cases) else 'INCOMPLETE' if counts.get('NOT RUN') or counts.get('INCONCLUSIVE') else 'FAIL'
    return {'schema_version': 1, 'status': status, 'pass': status == 'PASS', 'coverage_complete': False,
        'generated_utc': datetime.now(timezone.utc).isoformat(), 'metadata': metadata or {}, 'reporter_platform': platform.platform(),
        'identities': identities, 'cases': cases, 'counts': counts, 'observations': observations, 'timelines': timelines, 'errors': errors,
        'source_documents_sha256': sources, 'harness_sha256': {'behavior': behavior.get('harness_sha256'), 'instrumented': instrument.get('harness_sha256')},
        'limits': list(dict.fromkeys(behavior.get('limits', []) + instrument.get('limits', []) + ['Sequence is event order, not elapsed time.', 'PASS means required observed checks met their own expectations; legacy PASS is not a security verdict.', 'No report establishes all CVE variants as fixed.']))}


def render(model, template):
    # The data block cannot close its script tag, including hostile evidence strings.
    data = json.dumps(model, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return template.replace('__REPORT_DATA__', data)


def copy_evidence(source, target):
    """Keep logs/JSON/patches and harness provenance; exclude builds, sessions and archives."""
    if not source.exists(): return
    for path in source.rglob('*'):
        if path.is_symlink() or not path.is_file(): continue
        rel = path.relative_to(source)
        if any(part in ('install', 'probe', 'sessions', '.git') for part in rel.parts): continue
        if 'source' in rel.parts and not path.name.startswith('e2e-instrumentation.') and path.name != 'php70_e2e_trace.h': continue
        if path.suffix not in ('.json', '.log', '.patch', '.h', '.txt', '.py', '.sh', '.c', '.m4') and path.name != 'Dockerfile': continue
        dest = target / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, dest)


def write_report(model, output, template):
    output.mkdir(parents=True, exist_ok=False)
    (output / 'index.html').write_text(render(model, template))
    (output / 'report.html').write_text(render(model, template))
    (output / 'summary.json').write_text(json.dumps(model, ensure_ascii=False, indent=2) + '\n')
    lines = ['# PHP 7.0 E2E Evidence', '', '**Pipeline: ' + model.get('pipeline_status', model['status']) + ' · PHP: ' + model['status'] + '** · coverage_complete=false', '',
        'Source: `' + str(model['identities']['source_commit']['behavior']) + '`', '',
        '| Assertion status | Count |', '|---|---:|']
    lines += ['| ' + status + ' | ' + str(count) + ' |' for status, count in model['counts'].items()]
    lines += ['', 'Legacy PASS means expected legacy behavior, not a patched target.', 'Offline HTML and raw evidence are in the Actions Artifact. Pages is published only from main.']
    (output / 'job-summary.md').write_text('\n'.join(lines) + '\n')
    suite = ET.Element('testsuite', name='PHP E2E evidence', tests=str(len(model['cases']) + len(model['errors'])))
    for c in model['cases']:
        node = ET.SubElement(suite, 'testcase', classname=c['suite'] + '/' + c['mode'], name=c['name'])
        if c['status'] == 'SKIP': ET.SubElement(node, 'skipped', message=str(c['raw'].get('skip', '')))
        elif c['status'] != 'PASS': ET.SubElement(node, 'failure' if c['status'] == 'FAIL' else 'error', message=c['status']).text = json.dumps(c['raw'])
    for error in model['errors']:
        node = ET.SubElement(suite, 'testcase', classname='evidence', name=error['file'])
        ET.SubElement(node, 'error', message=error['error'])
    for key in ('detection', 'engine_detection'):
        detector = model.get(key)
        if not isinstance(detector, dict): continue
        for check in detector.get('checks', []):
            node = ET.SubElement(suite, 'testcase', classname=key, name=check.get('check', 'unnamed'))
            if check.get('pass') is not True: ET.SubElement(node, 'failure', message='Detection assertion failed').text = json.dumps(check)
        if detector.get('pass') is not True or detector.get('completed') is not True:
            node = ET.SubElement(suite, 'testcase', classname=key, name='Runner completion')
            ET.SubElement(node, 'error', message=str(detector.get('error', 'Detector incomplete')))
    suite.set('tests', str(len(suite.findall('testcase'))))
    suite.set('failures', str(len(suite.findall('./testcase/failure')))); suite.set('errors', str(len(suite.findall('./testcase/error')))); suite.set('skipped', str(len(suite.findall('./testcase/skipped'))))
    ET.ElementTree(suite).write(output / 'junit.xml', encoding='utf-8', xml_declaration=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--e2e', type=Path, required=True); p.add_argument('--trace', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--metadata', type=Path); p.add_argument('--detection', type=Path); p.add_argument('--engine', type=Path)
    a = p.parse_args()
    metadata = json.loads(a.metadata.read_text()) if a.metadata and a.metadata.exists() else {}
    for source in (a.e2e, a.trace, a.detection, a.engine):
        if source and (a.output.resolve() == source.resolve() or source.resolve() in a.output.resolve().parents): p.error('Report output must be outside input evidence trees')
    model = normalize(a.e2e, a.trace, metadata)
    if a.detection:
        try: model['detection'] = json.loads((a.detection / 'summary.json').read_text())
        except (OSError, ValueError) as exc: model['detection'] = {'pass': False, 'completed': False, 'status': 'NOT RUN', 'error': str(exc)}
    if a.engine:
        try: model['engine_detection'] = json.loads((a.engine / 'summary.json').read_text())
        except (OSError, ValueError) as exc: model['engine_detection'] = {'pass': False, 'completed': False, 'status': 'NOT RUN', 'error': str(exc)}
    detectors = [model[key] for key in ('detection', 'engine_detection') if key in model]
    model['pipeline_status'] = model['status'] if all(d.get('pass') is True and d.get('completed') is True for d in detectors) else 'FAIL'
    write_report(model, a.output, (Path(__file__).resolve().parents[1] / 'templates/report.html').read_text())
    copy_evidence(a.e2e, a.output / 'evidence/behavior'); copy_evidence(a.trace, a.output / 'evidence/instrumented')
    if a.detection: copy_evidence(a.detection, a.output / 'evidence/detection')
    if a.engine: copy_evidence(a.engine, a.output / 'evidence/openresty')
    files = {str(f.relative_to(a.output)): hashlib.sha256(f.read_bytes()).hexdigest() for f in a.output.rglob('*') if f.is_file()}
    (a.output / 'manifest.json').write_text(json.dumps({'files': files}, indent=2) + '\n')
    print(json.dumps({'status': model['status'], 'output': str(a.output)}))
    # Report generation succeeds even when tests failed. CI enforces model.pass separately.
    return 0

if __name__ == '__main__': raise SystemExit(main())
