# PHP 7.0.33 e2e 对照

从同一个已提交的 PHP PR revision 编译 legacy（`--disable-php70-security`）与 hardened（`--enable-php70-security`），另编译固定基线 `bf574c2b67a1f786e36cf679f41b758b973a82c4`。拒绝脏源码树，记录 commit、源码归档 SHA256、镜像 ID、工具链及 configure 日志。容器中不使用系统 PHP。

## 一键运行

需要 Docker、Git、Python 3。安装目录必须是 Linux 容器中编译的产物，不能把 macOS PHP 二进制直接挂到 Debian。

```sh
cd php-cve-e2e
./php70/run.sh --source ../php-src --output "$PWD/artifacts/run-001" --jobs 4
```

默认先构建工具链镜像（该步骤联网安装构建依赖），之后所有 PHP 编译/运行容器均 `--network none`。已有工具链可用：

```sh
./php70/run.sh --source ../php-src --output "$PWD/artifacts/run-002" \
  --reuse-image --image php70-security-toolchain:latest --jobs 4
```

输出目录必须尚不存在，不覆盖以前的证据。顺序执行 baseline、legacy、hardened；任一步骤失败退出非零，`summary.json` 保留 `pass=false`、`completed=false` 和错误。查看相应模式下的 build/native/FPM 日志。运行可能需要十几分钟和数 GB 磁盘。

不暴露 HTTP 端口：Python 客户端直接通过私有 FastCGI Unix socket 驱动本分支 FPM，覆盖真实 multipart 解析、session、RINIT 和请求收尾。省去 nginx 避免把 502/空响应误判成安全通过。FPM `pm=static`、`pm.max_children=1`、`pm.max_requests=0`；每次请求检查 master 存活，每个正常 JSON 回应检查 handler 与 HTTP globals。

## 检查和证据边界

| 项目 | 门禁 |
|---|---|
| 版本、模式 | PHP 7.0.33；测试扩展读取 hardened 标记，防止两套构建混用 |
| progress | 配置 On、cleanup Off，legacy/基线必须生成已知 session key；hardened 不生成，PHP_VALUE 再开启仍不生成 |
| 正常上传/session | 文件内容、字段、错误码、跨请求 session 计数均断言 |
| 普通 fatal | 三种构建均执行 shutdown，worker PID 不变；析构行为与固定基线实际结果一致；后续 handlers 与 globals 干净 |
| 脚本 OOM | hardened 无 shutdown/析构标记，worker PID 更换；legacy/基线 shutdown 被调用且 PID 复用 |
| 启动 multipart OOM | 32 MiB 普通字段对 16 MiB memory_limit；三种构建均换 PID，后续 session 连续可用 |
| allocator native | legacy/hardened 分别验证分配失败路径；hardened exit 1、无 PHP shutdown 和 C atexit 回调 |
| 请求边界 | 所有正常回应检测旧 error/exception handler 和带污染标记的 GET/POST/FILES，并确认数组类型 |

**不要把以下范围称作已动态证明：**

- session key 缺失只证明可观察 progress 行为。rfc1867 回调是否在 RINIT 前进入 session 逻辑，需要额外 C 层事件插桩/源码审查；当前工具不伪造这条证据。
- 启动期 OOM 发生在用户脚本运行前，没有机会注册本请求的 shutdown/析构。其标记缺失不能独立证明 `_exit`。native allocator 的 exit/atexit 检查是独立的补充证据，不能代替 FPM 启动期插桩。
- hardened OOM 后必须换 worker；不能同时要求“同 PID 请求 B”。同 PID 连续性在普通 fatal 路径验证，OOM 路径验证新 worker 的干净状态。
- HTTP globals 和 handler 检查是用户可观察回归探针，不证明所有内部字段都正确初始化。此工具不替代完整 PHPT/ASan。

## 来源与维护

`harness/` 从 php-src 的 `docs/security/testing/` 提取，保留原有 allocator probe、构建脚本和 FPM 边界用例，另增加析构、handler/global 状态、master 存活和失败 JSON。源码来源与文件摘要见 `PROVENANCE.json`。不修改 php-src。

测试扩展仅加载在隔离测试容器内。legacy 仅供对照，不作为生产回退。后续版本添加 `php71/` 等独立目录，不在 php70 中混入新版本兼容分支。

成功安装的三套构建可在修改测试工具后重复验证，无需重新编译：

```sh
python3 php70/verify-built.py --run artifacts/run-003 --output artifacts/recheck-001
```

新运行会把测试 harness 快照放在输出目录，记录文件 SHA256，防止测试过程中编辑工具导致证据混用。`pass=true` 表示已实现门禁通过；`coverage_complete=false` 明确表示上述 C 层生命周期范围尚未完整动态验证。

## C 层时序插桩

新增独立的 [trace-run.py](trace-run.py) 测试模式，在隔离源码副本中重新编译 legacy/hardened，动态记录 multipart、session 消费者及真实模块 RINIT 的顺序。方法、正对照、日志与适用范围见 [TRACE.md](TRACE.md)。原有报告的未验证标记保留；新的插桩证据保存在独立 `trace-*` 输出中。

## 分模式报告

统一入口：[非插桩行为报告 / 插桩时序报告](reports/README.md)。未来运行的汇总 JSON 使用 `report_mode` 和 `core_source_instrumented` 明确标记模式；已有原始报告保持不变，由 `reports/index.json` 建立关联。

## CI 集成

跨发行版与 cgroup 的共用入口及 PHPT 职责边界见 [CI 调用契约](CI.md)。
