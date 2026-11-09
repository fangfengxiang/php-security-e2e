#!/usr/bin/env python3
"""Fail-closed test-only source instrumentation, Linux NTS PHP 7.0 branch."""
from pathlib import Path
import difflib
import json
import hashlib
import sys
root=Path(sys.argv[1])
changes={}
def edit(path, old, new):
 p=root/path
 s=p.read_text()
 if s.count(old)!=1: raise RuntimeError('Anchor mismatch '+path+': '+old[:80])
 changes.setdefault(path,s)
 p.write_text(s.replace(old,new,1))
header='''/* Test-only Linux NTS observer. Never ship this build. */
#ifndef PHP70_E2E_TRACE_H
#define PHP70_E2E_TRACE_H
PHPAPI void php70_e2e_emit(const char *event, unsigned int detail);
PHPAPI void php70_e2e_begin(void);
PHPAPI void php70_e2e_rinit(void);
#endif
'''
(root/'main/php70_e2e_trace.h').write_text(header)
impl='''
/* Test-only: stack buffer + OS write, no Zend/session/global reads. */
#include "php70_e2e_trace.h"
#include <errno.h>
#include <unistd.h>
#include <stdlib.h>
static unsigned long php70_e2e_request;
static int php70_e2e_session_rinit;
static unsigned long php70_e2e_sequence;
PHPAPI void php70_e2e_emit(const char *event, unsigned int detail)
{
    int saved_errno = errno;
    ++php70_e2e_sequence;
    const char *path = getenv("PHP70_E2E_TRACE");
    if (path && *path) {
        char line[256];
        int length = snprintf(line, sizeof(line), "PHP70TRACE pid=%ld request=%lu rinit=%d seq=%lu event=%s detail=%u\\n",
            (long)getpid(), php70_e2e_request, php70_e2e_session_rinit, php70_e2e_sequence, event, detail);
        if (length > 0 && length < (int)sizeof(line)) {
            int fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0600);
            if (fd >= 0) {
                /* Missing/partial writes are rejected by the reader, not PHP. */
                ssize_t written = write(fd, line, length);
                (void)written;
                close(fd);
            }
        }
    }
    errno = saved_errno;
}
PHPAPI void php70_e2e_begin(void)
{
    ++php70_e2e_request;
    php70_e2e_session_rinit = 0;
    php70_e2e_sequence = 0;
    php70_e2e_emit("request.begin", 0);
}
PHPAPI void php70_e2e_rinit(void)
{
    php70_e2e_session_rinit = 1;
    php70_e2e_emit("session.module_rinit", 0);
}
'''
edit('main/main.c','/* {{{ php_request_startup\n */',impl+'\n/* {{{ php_request_startup\n */')
edit('main/main.c','#ifndef APACHE_HOOKS\nint php_request_startup(void)\n{\n\tint retval = SUCCESS;', '#ifndef APACHE_HOOKS\nint php_request_startup(void)\n{\n\tint retval = SUCCESS;\n\tphp70_e2e_begin();')
edit('main/main.c','\t\tzend_activate();\n\t\tsapi_activate();', '\t\tzend_activate();\n\t\tphp70_e2e_emit("sapi.activate.enter", 0);\n\t\tsapi_activate();\n\t\tphp70_e2e_emit("sapi.activate.leave", 0);')
# Use the request-startup occurrence only; other SAPI hook variants are out of scope.
p=root/'main/main.c';s=p.read_text();start=s.index('#ifndef APACHE_HOOKS\nint php_request_startup(void)');end=s.index('\n# else\nint php_request_startup(void)',start);tail=s[start:end];anchor='\t\tphp_hash_environment();'
if tail.count(anchor)!=1: raise RuntimeError('hash environment anchor mismatch')
tail=tail.replace(anchor,'\t\tphp70_e2e_emit("http_globals.enter", 0);\n'+anchor+'\n\t\tphp70_e2e_emit("http_globals.leave", 0);',1)
anchor='\t\tzend_activate_modules();'
if tail.count(anchor)!=1: raise RuntimeError('module activation anchor mismatch')
s=s[:start]+tail.replace(anchor,'\t\tphp70_e2e_emit("modules.activate.enter", 0);\n'+anchor+'\n\t\tphp70_e2e_emit("modules.activate.leave", 0);',1)+s[end:];p.write_text(s)
edit('ext/session/session.c','#include "php.h"','#include "php.h"\n#include "php70_e2e_trace.h"')
for signature,event in [('static void php_session_initialize(void)','session.initialize'),('static int php_rinit_session(zend_bool auto_start)','session.rinit_helper'),('static void php_session_rfc1867_early_find_sid(php_session_rfc1867_progress *progress)','progress.find_sid'),('static void php_session_rfc1867_update(php_session_rfc1867_progress *progress, int force_update)','progress.update'),('static void php_session_rfc1867_cleanup(php_session_rfc1867_progress *progress)','progress.cleanup')]:
 old=signature+' /* {{{ */\n{'
 edit('ext/session/session.c',old,old+'\n\tphp70_e2e_emit("'+event+'", 0);')
old='static PHP_RINIT_FUNCTION(session) /* {{{ */\n{'
edit('ext/session/session.c',old,old+'\n\tphp70_e2e_rinit();')
old='\tint retval = SUCCESS;\n\n\tif (php_session_rfc1867_orig_callback)'
edit('ext/session/session.c',old,'\tint retval = SUCCESS;\n\tphp70_e2e_emit("progress.callback", event);\n\n\tif (php_session_rfc1867_orig_callback)')
edit('ext/session/session.c','\tif (php70_security_is_hardened()) {\n\t\treturn retval;','\tif (php70_security_is_hardened()) {\n\t\tphp70_e2e_emit("progress.blocked", event);\n\t\treturn retval;')
edit('ext/session/session.c','\tprogress = PS(rfc1867_progress);','\tphp70_e2e_emit("progress.consume", event);\n\tprogress = PS(rfc1867_progress);')
patch=''.join(''.join(difflib.unified_diff(old.splitlines(True),(root/path).read_text().splitlines(True),fromfile='a/'+path,tofile='b/'+path)) for path,old in changes.items())
(root/'e2e-instrumentation.patch').write_text(patch)
(root/'e2e-instrumentation.json').write_text(json.dumps({'test_only':True,'platform':'Linux NTS','files':{path:{'before':hashlib.sha256(old.encode()).hexdigest(),'after':hashlib.sha256((root/path).read_bytes()).hexdigest()} for path,old in changes.items()},'added_header_sha256':hashlib.sha256(header.encode()).hexdigest()},indent=2)+'\n')
