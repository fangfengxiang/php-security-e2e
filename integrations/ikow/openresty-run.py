#!/usr/bin/env python3
"""Replay inert HTTP fixtures against actual OpenResty in an isolated container."""
import argparse,hashlib,json,subprocess,time,uuid
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--image',default='openresty/openresty:alpine-fat');a=p.parse_args()
root=Path(__file__).resolve().parent;out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);out.chmod(0o777)
origin=json.loads((root/'source.json').read_text())
name='php-e2e-detect-'+uuid.uuid4().hex[:12]
report={'pass':False,'completed':False,'kind':'detection_engine','engine':'OpenResty','upstream':origin,'input':'inert synthetic HTTP fixtures; no PHP backend','checks':[],
 'limits':['No PHP vulnerability or patch verdict is inferred from WAF behavior.','Suricata, Sigma, ModSecurity and full attack chains were not executed.','No bypass corpus or general false-positive/false-negative rate measured.']}
started=False
try:
 for path,meta in origin['files'].items():
  if hashlib.sha256((root/'upstream'/path).read_bytes()).hexdigest()!=meta['sha256']:raise RuntimeError('Upstream integrity mismatch')
 image=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',a.image],text=True).strip()
 report['image_id']=image
 subprocess.run(['docker','run','-d','--name',name,'--network','none','--read-only','--tmpfs','/tmp:rw,size=16m','--cap-drop=ALL','--security-opt=no-new-privileges','--user','65534:65534','-v',str(root)+':/integration:ro','-v',str(out)+':/evidence','--entrypoint','sh',image,'-ec','mkdir -p /tmp/e2e/body; exec openresty -p /tmp/e2e -c /integration/openresty.conf -g "daemon off;"'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 started=True
 report['engine_version']=subprocess.check_output(['docker','exec',name,'openresty','-V'],stderr=subprocess.STDOUT,text=True)
 for attempt in range(60):
  health=subprocess.run(['docker','exec',name,'curl','-fsS','http://127.0.0.1:8080/health'],capture_output=True,text=True)
  if health.returncode==0 and 'BACKEND_FIXTURE_REACHED' in health.stdout:break
  time.sleep(.1)
 else:raise RuntimeError('OpenResty health check failed')
 cases=[('ordinary upload','POST','/probe','safe.txt','hello',200,None),('progress field blocked','POST','/probe','safe.txt','PHP_SESSION_UPLOAD_PROGRESS',403,'blocked PHP_SESSION_UPLOAD_PROGRESS'),('session id alerts only','POST','/probe','safe.txt','name="PHPSESSID"',200,'PHPSESSID in POST body'),('PHP signature blocked','POST','/probe','<?php /* inert marker */ ?>','hello',403,'PHP code in upload filename'),('log only does not block','POST','/log-only','safe.txt','PHP_SESSION_UPLOAD_PROGRESS',200,'blocked PHP_SESSION_UPLOAD_PROGRESS'),('GET is skipped','GET','/probe','safe.txt','PHP_SESSION_UPLOAD_PROGRESS',200,None)]
 log=out/'nginx-error.log'
 for label,method,url,filename,value,expected,alert in cases:
  before=log.read_text(errors='replace') if log.exists() else ''
  body=('--fixture\r\nContent-Disposition: form-data; name="file"; filename="'+filename+'"\r\n\r\n'+value+'\r\n--fixture--\r\n')
  proc=subprocess.run(['docker','exec','-i',name,'curl','-sS','-D','-','-w','\n%{http_code}','-X',method,'-H','Content-Type: multipart/form-data; boundary=fixture','--data-binary','@-','http://127.0.0.1:8080'+url],input=body,text=True,capture_output=True,timeout=10,check=True)
  raw,status=proc.stdout.rsplit('\n',1);observed=int(status)
  newlog=log.read_text(errors='replace')[len(before):]
  passed=observed==expected and (('BACKEND_FIXTURE_REACHED' in raw)==(expected==200)) and (alert in newlog if alert else 'php2shell:' not in newlog)
  if expected==403:passed=passed and 'x-blocked-by: php2shell-detection' in raw.lower()
  report['checks'].append({'check':label,'pass':passed,'expected_status':expected,'observed_status':observed,'response':raw,'detector_log':newlog})
 if not all(c['pass'] for c in report['checks']):raise RuntimeError('Unexpected engine result')
 report.update({'pass':True,'completed':True})
except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)
finally:
 if started:
  logs=subprocess.run(['docker','logs',name],capture_output=True,text=True);(out/'container.log').write_text(logs.stdout+logs.stderr)
  subprocess.run(['docker','rm','-f',name],capture_output=True)
 (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'pass':report['pass'],'output':str(out),'error':report.get('error')}))
raise SystemExit(0 if report['pass'] else 1)
