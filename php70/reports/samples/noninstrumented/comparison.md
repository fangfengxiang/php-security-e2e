# 修复版与非修复版：本轮实测差异

本轮复用已编译的 PHP 7.0.33 安装，重新执行真实容器 FPM/native 探针；没有重新编译。
baseline 为固定基线，legacy/hardened 来自同一 PR 提交的不同编译配置。

| 检查 | baseline | legacy | hardened |
|---|---|---|---|
| 出现 upload_progress key | True | True | False |
| 脚本 OOM 执行 shutdown | True | True | False |
| 脚本 OOM 执行析构 | False | False | False |
| master 存活 | True | True | True |
| 启动期 OOM child exit code | 70 | 70 | 1 |
| 普通 fatal 执行 shutdown | True | True | True |
| 普通 fatal 执行析构 | False | False | False |
| 符合已观察 hardened 行为门禁 | False | False | True |

脚本 OOM PID：baseline: 10 → 10；legacy: 10 → 10；hardened: 9 → 10

各容器 PID 是各自命名空间内的值，仅比较同一容器请求前后。
三种模式的测试 PASS 表示符合各自预期，并不表示三种模式都已修复。按统一 hardened 行为门禁重新判断，只有 hardened 通过。
普通上传、session 连续读写、fatal 后同 worker handler/global 状态检查均通过。
RINIT 前 session 消费顺序仍无 C 层动态插桩证据；启动期用户脚本尚未执行，不能把缺少用户标记当作独立证明。

完整报告见 summary.json、各模式 fpm/native JSON 和原始日志。
