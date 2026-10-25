# RINIT 前 session 消费的 C 层动态观测

此模式只在从已提交源码归档解出的隔离副本中插桩并重新编译。`php-src` 不变，普通 `run.sh` 不应用插桩。插桩产物仅用于测试，不能部署到生产。

```sh
cd php-security-e2e
python3 php70/trace-run.py --source ../php-src \
  --output "$PWD/artifacts/trace-new" --image php70-security-toolchain:latest --jobs 6
```

使用已经准备的构建镜像；可给 `--image` 传镜像 ID。编译和测试容器无网络。输出目录必须新建。分别从同一源码提交构建 legacy 和 hardened；每种构建运行 4 个时序请求，以及原有 12 项 FPM 回归检查。

## 观察点

| C 入口/路径 | 日志事件 | 用途 |
|---|---|---|
| `php_request_startup` | `request.begin` | 新请求序号，并重置观测器自己的 RINIT 标志 |
| `sapi_activate` 前后 | `sapi.activate.enter/leave` | 标出 SAPI 激活阶段边界，避免预设 multipart 在该函数内消费 |
| `php_hash_environment` 前后 | `http_globals.enter/leave` | 标出实际 HTTP globals 构造及 multipart 消费阶段 |
| `zend_activate_modules` 前后 | `modules.activate.enter/leave` | 确定模块 RINIT 执行阶段 |
| `PHP_RINIT_FUNCTION(session)` | `session.module_rinit` | 真正的 session 模块 RINIT 入口；不与内部 helper 混淆 |
| `php_rinit_session` | `session.rinit_helper` | 识别上传回调提前调用内部初始化 helper |
| `php_session_rfc1867_callback` | `progress.callback` | 记录全部 multipart 回调阶段编号 0–5 |
| hardened 提前返回 | `progress.blocked` | 每个 callback 都必须对应阻断事件 |
| enabled 检查后的 progress 状态路径 | `progress.consume` | 识别进入 session progress 消费路径 |
| SID 解析/update/cleanup | `progress.find_sid/update/cleanup` | 进一步定位消费者 |
| `php_session_initialize` | `session.initialize` | 记录真正进入 session 初始化的位置 |

日志包含 PID、单 worker 内的请求序号、模块 RINIT 是否已进入、连续事件序号、事件名和 multipart 阶段。连续序号用于拒绝中途漏行或乱序。观测器只读取自己的静态状态，使用栈上格式化和 OS 文件 append 写入，保存/恢复 errno；不调用 Zend allocator，不读取尚未初始化的 PHP/session globals。

## 成功判定

1. 同一个 worker 连续完成：普通 session → multipart → multipart + `PHP_VALUE` 开启 progress → 普通 session，session 计数连续递增。
2. 普通 session 请求必须观测到模块 RINIT **之后**的 `session.initialize`，作为 C 入口探针有效的正对照。
3. legacy multipart 必须观测到模块 RINIT **之前**的 progress 消费、内部初始化 helper 和 `session.initialize`，作为提前消费的正对照。
4. hardened multipart 必须观测到完整 0–5 阶段 callback，均位于 `php_hash_environment` 内、`sapi_activate` 返回之后且早于模块 RINIT；每个 callback 都出现 blocked，且 RINIT 前无任何已插桩消费者。随后脚本期普通 session 初始化仍可用。
5. 缺失关键事件、损坏日志、空/无效响应、PID/session 连续性失效或门禁失败，均返回非零，不把无日志当作通过。

每种模式保存 `trace.json`、`trace.events.log`、FPM 日志；`source/e2e-instrumentation.patch` 和 `source/e2e-instrumentation.json` 保留插桩改动及源文件前后 SHA256；`summary.json` 保存源码提交、镜像 ID、harness 快照 SHA256、各项结果。

## 适用范围

这是 Linux NTS FPM 的受控动态证据，覆盖此测试的已插桩 session 路径。未加载第三方 rfc1867 callback，不推断第三方扩展行为。额外写日志可能影响时间/内存布局，因此须与原来的无插桩结果并存。这个模式补充 pre-RINIT 消费时序证据，不宣称完成 OOM 全部内部生命周期或完整 CVE 利用链验证。

## 本轮实测

`artifacts/trace-003`：8 个时序请求、24 项 FPM 回归全部通过。每个 multipart 请求 legacy 在模块 RINIT 前有 15 个消费者事件，其中 session.initialize 2 次；hardened 观察到 7 次 callback 和 7 次 blocked，RINIT 前消费者为 0。PHP_VALUE 开启 progress 的请求结果相同。关键行为签名与 `artifacts/recheck-002` 的无插桩结果相同，详见输出目录 comparison.md。

侵入性：尽管原工作目录不变，测试副本的源码及二进制确实被修改。额外的 getenv、snprintf、open/write/close 会改变代码/数据布局、系统调用和调度；libc 内部也可能分配内存。没有调用 Zend allocator 不等于零分配或零干扰。该证据仅用于受测同步控制流的路径/顺序，不证明原始堆布局、竞态概率、精确性能、OOM 阈值或 RCE 可利用性。
