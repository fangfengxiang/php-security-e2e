#!/usr/bin/env python3
"""Observe real FPM request ordering in a test-only instrumented Linux NTS build."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import signal
import subprocess
import tempfile
import time


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--fpm',required=True)
 p.add_argument('--output',type=Path,required=True)
 p.add_argument('--legacy',action='store_true')
 a=p.parse_args()
 client=runpy.run_path(str(Path(__file__).with_name('fpm-invariants.py')),run_name='fastcgi_client')
 report={'pass':False,'completed':False,'legacy':a.legacy,'instrumented_build':True,'requests':[]}
 output=a.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
 process=None
 try:
  with tempfile.TemporaryDirectory(prefix='php70-trace-',dir='/tmp') as directory:
   root=Path(directory);root.chmod(0o777)
   sessions=root/'sessions';sessions.mkdir();sessions.chmod(0o777)
   trace=root/'events.log';address=root/'fpm.sock'
   script=root/'probe.php'
   script.write_text('''<?php
if (PHP_VERSION_ID !== 70033 || PHP_ZTS) { exit('WRONG BUILD'); }
session_id('tracesession'); session_start();
$_SESSION['count'] = isset($_SESSION['count']) ? $_SESSION['count'] + 1 : 1;
$keys = array_keys($_SESSION); $progress = false;
foreach ($keys as $key) { if (strpos($key, 'upload_progress_') === 0) { $progress = true; } }
$result = array('pid'=>getmypid(), 'count'=>$_SESSION['count'], 'has_progress'=>$progress,
 'post'=>$_POST, 'upload'=>isset($_FILES['upload']) ? array('error'=>$_FILES['upload']['error'],
 'data'=>file_get_contents($_FILES['upload']['tmp_name'])) : null);
session_write_close(); header('Content-Type: application/json'); echo json_encode($result);
''')
   config=root/'fpm.conf'
   config.write_text('''[global]
daemonize = no
error_log = {root}/fpm.log
[probe]
user = nobody
group = nogroup
listen = {socket}
pm = static
pm.max_children = 1
pm.max_requests = 0
clear_env = no
catch_workers_output = yes
php_admin_value[memory_limit] = 16M
php_admin_value[session.save_path] = {sessions}
php_admin_value[session.upload_progress.enabled] = 1
php_admin_value[session.upload_progress.cleanup] = 0
php_admin_value[session.upload_progress.min_freq] = 0
php_admin_value[display_errors] = 0
'''.format(root=root,socket=address,sessions=sessions))
   env=dict(os.environ,PHP70_E2E_TRACE=str(trace))
   env.pop('USE_ZEND_ALLOC',None)
   with output.with_suffix('.process.log').open('wb') as log:
    process=subprocess.Popen([a.fpm,'-n','-F','-R','-y',str(config)],env=env,stdout=log,stderr=log)
    try:
     for unused in range(200):
      if address.exists(): break
      if process.poll() is not None: raise RuntimeError('FPM exited on startup')
      time.sleep(0.05)
     else: raise RuntimeError('FPM socket timeout')
     pattern=re.compile(r'PHP70TRACE pid=(\d+) request=(\d+) rinit=([01]) seq=(\d+) event=([a-z._]+) detail=(\d+)')
     pid=None
     for ordinal,scenario in enumerate(('normal-before','multipart','multipart-php-value','normal-after'),1):
      kwargs={}
      if scenario.startswith('multipart'):
       body,kind=client['multipart']([('PHPSESSID',b'tracesession',None),('PHP_SESSION_UPLOAD_PROGRESS',b'trace',None),('upload',b'trace upload\n','trace.txt')])
       kwargs.update(body=body,content_type=kind)
       if scenario.endswith('php-value'): kwargs['extra_params']={'PHP_VALUE':'session.upload_progress.enabled=1'}
      response=client['request'](address,script,**kwargs)
      data=client['result_json'](response)
      if not response['ended']: raise RuntimeError('Missing FastCGI END_REQUEST')
      if pid is None: pid=data['pid']
      if data['pid']!=pid or data['count']!=ordinal: raise RuntimeError('Worker/session continuity lost')
      if process.poll() is not None: raise RuntimeError('Master exited')
      events=[]
      for line in trace.read_text().splitlines():
       match=pattern.fullmatch(line)
       if not match: raise RuntimeError('Malformed/partial trace line: '+line)
       ep,req,rinit,sequence,event,detail=match.groups()
       if int(ep)==pid and int(req)==ordinal: events.append({'event':event,'rinit':int(rinit),'sequence':int(sequence),'detail':int(detail)})
      if [e['sequence'] for e in events]!=list(range(1,len(events)+1)): raise RuntimeError('Trace gap or reorder')
      names=[e['event'] for e in events]
      for name in ('request.begin','sapi.activate.enter','sapi.activate.leave','http_globals.enter','http_globals.leave','modules.activate.enter','session.module_rinit','modules.activate.leave'):
       if names.count(name)!=1: raise RuntimeError('Missing/duplicate '+name)
      if not (names.index('request.begin') < names.index('sapi.activate.enter') < names.index('sapi.activate.leave') < names.index('http_globals.enter') < names.index('http_globals.leave') < names.index('modules.activate.enter') < names.index('session.module_rinit') < names.index('modules.activate.leave')):
       raise RuntimeError('Invalid lifecycle ordering')
      rinit_index=names.index('session.module_rinit')
      early=[e for e in events[:rinit_index] if e['event'] in ('progress.consume','progress.find_sid','progress.update','progress.cleanup','session.rinit_helper','session.initialize')]
      late_initializers=[i for i,e in enumerate(events) if e['event']=='session.initialize' and i>rinit_index and e['rinit']==1]
      if not late_initializers: raise RuntimeError('Missing post-RINIT session positive control')
      callbacks=[(i,e) for i,e in enumerate(events) if e['event']=='progress.callback']
      if scenario.startswith('multipart'):
       if data['upload']!={'error':0,'data':'trace upload\n'}: raise RuntimeError('Upload failed')
       if set(e['detail'] for i,e in callbacks)!=set(range(6)): raise RuntimeError('Missing multipart callback phase')
       if any(not(names.index('http_globals.enter')<i<names.index('http_globals.leave')) or e['rinit']!=0 for i,e in callbacks): raise RuntimeError('Callback outside pre-RINIT HTTP globals construction')
       if a.legacy:
        if not early or not any(e['event']=='session.initialize' for e in early) or not any(e['event']=='session.rinit_helper' for e in early): raise RuntimeError('Missing legacy early-consumer positive control')
        if 'progress.blocked' in names or not data['has_progress']: raise RuntimeError('Legacy behavior mismatch')
       else:
        blocked=[e for e in events if e['event']=='progress.blocked']
        if early or len(blocked)!=len(callbacks) or data['has_progress']: raise RuntimeError('Hardened early session consumption or missing blocker')
        if [e['detail'] for e in blocked]!=[e['detail'] for i,e in callbacks]: raise RuntimeError('Blocked phases differ from callbacks')
      elif callbacks or early:
       raise RuntimeError('Normal request unexpectedly consumed multipart state')
      report['requests'].append({'scenario':scenario,'pid':pid,'ordinal':ordinal,'data':data,'early_consumers':early,'events':events,'pass':True})
     report['pass']=True;report['completed']=True
    finally:
     if process.poll() is None:
      process.send_signal(signal.SIGTERM)
      try: process.wait(timeout=10)
      except subprocess.TimeoutExpired: process.kill();process.wait()
     if trace.exists(): output.with_suffix('.events.log').write_bytes(trace.read_bytes())
     if (root/'fpm.log').exists(): output.with_suffix('.fpm.log').write_bytes((root/'fpm.log').read_bytes())
 except Exception as error:
  report['error']=type(error).__name__+': '+str(error)
 finally:
  output.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'pass':report['pass'],'output':str(output),'error':report.get('error')}))
 return 0 if report['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
