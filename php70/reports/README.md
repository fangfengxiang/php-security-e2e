# PHP 7.0.33：分模式验证报告

两类报告分别判定，不能用插桩通过覆盖非插桩失败，也不能把“未观测”写成“已证明”。以下索引关联已有真实运行，没有重新执行或修改原始测试记录。

| 报告模式 | PHP 核心源码 | 主要用途 | 最新已验证结果 |
|---|---|---|---|
| 非插桩行为报告 | 未加入 C 日志插桩；native allocator 检查会加载测试扩展 | 外部行为、安全门禁和回归 | [行为差异](samples/noninstrumented/comparison.md) · [完整 JSON](samples/noninstrumented/summary.json) |
| 插桩时序报告 | 在隔离副本加入 C 日志并重新编译 | 内部路径到达性、RINIT 前后顺序 | [时序与干扰边界](samples/instrumented/comparison.md) · [完整 JSON](samples/instrumented/summary.json) |

## 非插桩行为报告

受测版本：PHP 7.0.33。baseline 是固定基线；legacy/hardened 来自同一适配分支的不同编译配置。

- 36 项 FPM 检查、26 项 native 检查符合各自预期。
- hardened 不生成 upload_progress key；脚本 OOM 不执行 shutdown/析构，worker 更换，master 存活。
- legacy/基线生成 progress key；脚本 OOM 执行 shutdown，worker 复用。
- 普通 fatal 的 shutdown/析构行为与基线一致，普通上传、session、可观察跨请求状态检查通过。
- FPM 行为检查不加载 native 测试扩展；native allocator 检查单独加载 security_probe.so。非插桩指未修改 PHP 核心源码，不表示测试完全没有额外探针。
- 此报告不独立证明内部 RINIT 消费时序。

运行入口：`php70/run.sh`；复验入口：`php70/verify-built.py`。

## 插桩时序报告

受测版本：同一分支提交的 PHP 7.0.33，另建测试副本，分别编译 legacy/hardened；原 php-src 工作目录未修改。

- 8 个时序请求、24 项 FPM 回归检查通过。
- 每个受测 multipart 请求：legacy 在真实 session 模块 RINIT 前进入 session.initialize 两次；hardened 为零，7 次 callback 均有 blocked。
- 普通 session 是 RINIT 后初始化的正对照；同 worker 请求序号和连续事件序号经过检查。
- progress、普通 fatal、脚本 OOM 的关键行为签名与非插桩结果一致。
- 插桩改变布局、系统调用和调度；结果不证明原始堆布局、竞态概率、精确 OOM 阈值或 RCE 可利用性。没有第三方 callback 的动态覆盖。

运行入口：`php70/trace-run.py`；[插桩方法](../TRACE.md)。

## 联合判读

当前结论是：非插桩模式测出了修复前后的行为差异；插桩模式补充了受测请求中阻断提前 session 消费的内部时序证据。两者是互补证据，不合并成“全部范围已验证”。历史报告中的 coverage_complete=false 保留。
