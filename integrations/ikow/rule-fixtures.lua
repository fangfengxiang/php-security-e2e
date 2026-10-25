-- Unit-level execution of the unchanged upstream Lua rule. ngx is a test double.
-- No network, PHP execution, shell payload, or target URL is used.
local rule = dofile(arg[1])
local cases = {
 {name='ordinary upload',body='name="file"; filename="safe.txt"\r\nhello',status=200,alerts=0},
 {name='progress field blocked',body='name="PHP_SESSION_UPLOAD_PROGRESS"\r\nprobe',status=403,alerts=1},
 {name='session id alerts only',body='name="PHPSESSID"\r\nprobe',status=200,alerts=1},
 {name='PHP signature blocked',body='name="file"; filename="<?php /* inert marker */ ?>"',status=403,alerts=1},
 {name='log only does not block',body='name="PHP_SESSION_UPLOAD_PROGRESS"\r\nprobe',status=200,alerts=1,log_only=true},
 {name='GET is skipped',body='PHP_SESSION_UPLOAD_PROGRESS',method='GET',status=200,alerts=0}
}
for _,case in ipairs(cases) do
 local logs,code={},200
 ngx={WARN=4,var={remote_addr='127.0.0.1',request_uri='/unit-fixture'},header={},req={}}
 ngx.req.get_method=function() return case.method or 'POST' end
 ngx.req.get_headers=function() return {['content-type']='multipart/form-data; boundary=fixture'} end
 ngx.req.read_body=function() end
 ngx.req.get_body_data=function() return case.body end
 ngx.req.get_body_file=function() return nil end
 ngx.log=function(_,...) logs[#logs+1]=table.concat({...}) end
 ngx.say=function() end
 ngx.exit=function(status) code=status;return status end
 rule.check({log_only=case.log_only})
 if code~=case.status or #logs~=case.alerts then error(case.name..': unexpected status or alert count') end
 print(case.name..'\t'..code..'\t'..#logs)
end
