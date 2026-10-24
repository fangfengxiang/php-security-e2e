# 公开实测样例

运行日期：2026-10-24；整理日期：2026-10-25。来自实际隔离容器运行，不是模拟输出，也不是再次执行。

- [非插桩行为报告](noninstrumented/comparison.md)：完整 JSON、native 输出与 FPM 原始日志。
- [插桩时序报告](instrumented/comparison.md)：完整 JSON、C 事件日志、FPM 回归日志、确切补丁及新增 C header。
- [公开副本清单](PUBLICATION.json)：列出原始文件与公开副本 SHA256，仅本机绝对路径被替换，观测和断言不变。

未发布源代码归档、完整 PHP 构建树或二进制。JSON 中历史输出位置保留为环境证据，不保证可在新机器访问。两个模式的历史 coverage 限制保持原样，后续插桩证据独立补充，不倒改旧报告为完整验证。
