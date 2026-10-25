#!/usr/bin/env python3
"""Maintain explicit Pages history in a dedicated branch checkout."""
import argparse
import html
import json
from pathlib import Path
import re
import shutil

p=argparse.ArgumentParser();p.add_argument('--site',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--run-id',required=True);p.add_argument('--attempt',required=True);a=p.parse_args()
if not re.fullmatch(r'\d+',a.run_id) or not re.fullmatch(r'\d+',a.attempt):p.error('Numeric run identity required')
site=a.site;site.mkdir(parents=True,exist_ok=True)
key=a.run_id+'-'+a.attempt
destination=site/'runs'/key
if destination.exists():raise SystemExit('Refusing to overwrite a historical run')
shutil.copytree(a.report,destination)
model=json.loads((a.report/'summary.json').read_text())
index=site/'history.json';history=json.loads(index.read_text()) if index.exists() else []
history.insert(0,{'run':key,'status':model.get('pipeline_status', model['status']),'php_status':model['status'],'source_commit':model['identities']['source_commit']['behavior'],'generated_utc':model['generated_utc']})
index.write_text(json.dumps(history,indent=2)+'\n')
# Both files are generated from identical test data; embedded charts remain self-contained.
for name in ('index.html','report.html','summary.json','manifest.json','junit.xml','job-summary.md'):
 shutil.copy2(destination/name,site/name)
# Root evidence is the latest run's evidence, including failure/incomplete runs.
if (site/'evidence').exists():shutil.rmtree(site/'evidence')
if (destination/'evidence').exists():shutil.copytree(destination/'evidence',site/'evidence')
rows=''.join('<tr><td><a href="runs/'+html.escape(row['run'])+'/index.html">'+html.escape(row['run'])+'</a></td><td>'+html.escape(row['status'])+'</td><td>'+html.escape(str(row['source_commit']))+'</td><td>'+html.escape(row['generated_utc'])+'</td></tr>' for row in history)
(site/'history.html').write_text('<!doctype html><meta charset="utf-8"><title>PHP Security E2E history</title><h1>PHP Security E2E report history</h1><p><a href="index.html">Latest run, including failures</a></p><table><tr><th>Run / attempt</th><th>Status</th><th>PHP source</th><th>Generated UTC</th></tr>'+rows+'</table>')
(site/'.nojekyll').touch()
