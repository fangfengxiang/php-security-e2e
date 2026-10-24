# 当前适配分支的静态证据

受测提交：`5c9173b159d4ddcd82a016e8ba6220d545740bbb`；固定基线：`bf574c2b67a1f786e36cf679f41b758b973a82c4`。

这份记录属于源码审查，不是运行时插桩记录；替换 `--ref` 后需重新审查。

- `ext/session/session.c:2955` 的 `php_session_rfc1867_callback` 先保留原 callback chaining，再检查 `php70_security_is_hardened()` 并立即返回。对当前函数自身而言，这个返回位于 `PS(rfc1867_enabled)`、`PS(rfc1867_progress)` 和后面的 `php_rinit_session(0)` 之前，静态支持 hardened 不进入本函数 session progress 消费逻辑。它不证明第三方 callback 的行为；当前工具没有动态追踪每一次 C 函数调用。
- `Zend/zend_alloc.c` 的 hardened 分配失败分支使用 `_exit(1)`。native 测试扩展触发有界失败/溢出边界，要求 exit 1，且不观察到 PHP shutdown、析构和 C atexit 回调；FPM 另要求 master 日志中的 child exit 1、新 PID 与正常恢复。这些证据结合支持 fail-stop 行为，单独 PID 改变不足以证明它。
- 启动期 multipart 分配失败在用户脚本之前发生；前一请求注册的用户 shutdown handler 已在其生命周期结束时清理。没有确定的跨请求生产者/消费者证据时，不能把假设残留状态报告为已确认漏洞。当前测试验证同 PID fatal 后的用户可观察状态，以及 OOM 后新 PID 的可用性，不修改运行时代码。

本工具从既有测试基础抽出；没有把 Grok 方案中“请求异常即成功”“标记出现只警告”作为门禁。连接失败、无效 JSON、超时、断言失败均非零退出。
