# C 层插桩实测与干扰边界

原 php-src 工作目录未修改。测试副本 C 源码及二进制被修改：这是侵入式源码插桩。
从同一提交分别重编译 legacy/hardened，全部 8 个时序请求、24 项 FPM 回归检查通过。

| 模式 | 请求 | callback 数 | blocked 数 | RINIT 前消费者事件 | RINIT 前 session.initialize |
|---|---|---:|---:|---:|---:|
| legacy | multipart | 7 | 0 | 15 | 2 |
| legacy | multipart-php-value | 7 | 0 | 15 | 2 |
| hardened | multipart | 7 | 7 | 0 | 0 |
| hardened | multipart-php-value | 7 | 7 | 0 | 0 |

legacy 的实际顺序：`sapi.activate.leave → http_globals.enter → progress.callback/consume → session.rinit_helper → session.initialize → http_globals.leave → session.module_rinit`。
hardened 的实际顺序：`http_globals.enter → progress.callback/blocked → http_globals.leave → session.module_rinit → session.initialize`。
两种模式最后的普通 session 请求都正常；同一 worker 连续请求序号和事件序号已检查。

与 artifacts/recheck-002 的无插桩结果对照：progress、普通 fatal、脚本 OOM 的 shutdown/析构、worker 更换及 master 存活等行为签名相同。

插桩改变可执行文件/数据布局，新增 getenv、snprintf、open/write/close，可能引发 libc 内部行为并影响调度。没有调用 Zend allocator 或修改 PHP/session globals，不等于零内存分配或零干扰。
因此，本结果用于已插桩同步路径的到达性与先后顺序；不用于证明原始堆布局、竞态概率、精确性能、OOM 阈值或 RCE 可利用性。需要同时参考无插桩门禁和源码控制流。

原始事件见 legacy/trace.events.log 与 hardened/trace.events.log；确切补丁见各模式 source/e2e-instrumentation.patch。未加载第三方 rfc1867 回调，不将本结果泛化到第三方扩展。
