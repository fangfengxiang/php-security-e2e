# Evidence → HTML → Actions / Pages / Artifact

`tools/report.py` 使用 Python 标准库读取原始证据，生成自包含 HTML：无 CDN、无 fetch、无 Node 依赖。覆盖矩阵是实际断言；行为差分展示观察值；生命周期 SVG 展示完整 sequence，不换算毫秒。点击矩阵单元格或事件可查看内嵌原始记录。

```sh
python3 tools/report.py \
  --e2e php70/reports/samples/noninstrumented \
  --trace php70/reports/samples/instrumented \
  --output artifacts/historical-preview
```

打开输出 `index.html` 或 `report.html` 即可离线查看。以上命令只使用 2026-10-24 历史证据，不会执行 PHP 或伪造新的运行结果。真实运行改为传入本轮 behavior/trace 输出目录。`--metadata` 可传入 CI 源码/runner 身份 JSON；`--detection` 附加独立 ikow 规则单元结果，`--engine` 附加真实 OpenResty HTTP 回放。PHP 状态、检测状态与 pipeline_status 分开保存，JUnit 使用独立 classname。

输出：HTML、标准化 summary.json、JUnit、job-summary.md、evidence/ 与 manifest.json。读取不覆盖原始证据。归档保留 JSON、日志、构建日志、harness 和插桩补丁，排除完整源码树、安装二进制、session 与 tar 归档。

缺失/损坏 JSON、源码身份不一致、未完成 runner、事件序号缺口不会变成 PASS。预期计划未完成显示 NOT RUN；存在 trace 但不可判定显示 INCONCLUSIVE；顶层结果可为 PASS、FAIL、INCOMPLETE。所有行为门禁的 PASS 仍保留 coverage_complete=false。生成报告的退出码表示“能否生成报告”，不是 PHP 测试成功；工作流在归档后独立强制检查测试退出码和报告结果。

## GitHub 三种展示

- Job Summary：本轮状态、实际断言计数、Artifact/Pages 入口。
- Artifact：90 天保留，自包含 HTML + 原始证据。下载后打开 HTML；GitHub 不会在线执行 Artifact 中的 HTML。
- Pages：main 的每次可生成报告的运行均发布，包括失败/未完成。PR 不发布公开 Pages。`index.html` 展示最近发布运行；`runs/<run-id>-<attempt>/index.html` 保留历史；`history.html` 为执行索引。

历史文件明确存入 `e2e-pages` 分支，而非依赖 Pages 自动保存。该分支不触发 main 测试。Artifact 和 Pages 使用同一份下载的报告数据；发布只添加导航历史，不重算或修改断言。

## CI

`.github/workflows/php70-e2e-report.yml`：push main、pull_request、手工执行、每周一 03:00 UTC（北京时间 11:00）。检出 `fangfengxiang/php-src` 的 `refs/pull/1/head`，完整取历史以构建固定基线，实际 head 写入 run-metadata.json。Legacy/Hardened 使用同一个检出，不固定到一份过期 SHA。

顺序运行 3 种非插桩构建，再运行 2 种插桩构建，不新增平台矩阵。全部构建和测试位于无网络容器，只有工具链镜像/依赖准备联网。缺少工具链时 Trace 会失败并保留未完成状态。

需要仓库 Pages 的 build_type 为 workflow；部署 job 使用 pages:write、id-token:write，只有维护历史分支的 job 拥有 contents:write。PR 测试只给 contents:read。首次真实 CI 是否成功应查看 Actions；历史样例预览不等同于新 CI 结果。

## ikow 接入边界

见 [integrations/ikow](../integrations/ikow/README.md)。检测规则单元检查、真实 OpenResty HTTP 回放单独展示；Suricata/Sigma/ModSecurity、完整 A–E 利用链仍为 NOT RUN。既有 PHP 修复门禁不因某条 WAF 规则命中而通过。
