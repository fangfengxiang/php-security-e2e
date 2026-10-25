#!/usr/bin/env python3
"""Integrity-pinned upstream Lua rule unit checks; not PHP exploit or deployed WAF coverage."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--lua',default='lua');a=p.parse_args()
root=Path(__file__).resolve().parent;origin=json.loads((root/'source.json').read_text())
a.output.mkdir(parents=True,exist_ok=False)
report={'pass':False,'completed':False,'kind':'detection_rule_unit','ngx':'test_double','input':'synthetic inert fixtures','upstream':origin,'checks':[],
 'attack_paths':{key:{'status':'NOT RUN','note':note} for key,note in {'A':'Session/LFI full chain not executed; existing progress gates test a prerequisite only.','B':'var_destroy/unserialize exploit not executed.','C':'Handler-mismatch chain not executed.','D':'mod_php not supported by current PHP70 suite.','E':'Full FPM stale-state exploit not executed; existing OOM/session gates cover selected behavior only.'}.items()},
 'engines':{'openresty_lua':'unit runtime only; not an OpenResty deployment','suricata':'IMPORTED / NOT RUN','sigma':'IMPORTED / NOT RUN','modsecurity':'IMPORTED / NOT RUN'}}
try:
 for path,meta in origin['files'].items():
  if hashlib.sha256((root/'upstream'/path).read_bytes()).hexdigest()!=meta['sha256']:raise RuntimeError('Upstream integrity mismatch: '+path)
 lua=shutil.which(a.lua)
 if not lua:raise RuntimeError('Lua runtime missing; rules were not executed')
 result=subprocess.run([lua,str(root/'rule-fixtures.lua'),str(root/'upstream/detection/php2shell.lua')],text=True,capture_output=True,timeout=20)
 (a.output/'lua.log').write_text(result.stdout+result.stderr)
 if result.returncode:raise RuntimeError('Lua rule unit check failed')
 for line in result.stdout.splitlines():
  name,status,alerts=line.split('\t');report['checks'].append({'check':name,'status_code':int(status),'alerts':int(alerts),'pass':True})
 if len(report['checks'])!=6:raise RuntimeError('Incomplete fixture execution')
 report.update({'pass':True,'completed':True})
except Exception as e:report['error']=str(e)
(a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'pass':report['pass'],'output':str(a.output)}))
sys.exit(0 if report['pass'] else 1)
