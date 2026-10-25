# PHP 7.0 CI 调用契约

php-src 保留 PHP 源码、所有 PHPT、run-tests.php、测试选择与 PHPT 门禁。
php-cve-e2e 维护工具链、构建、native probe、FPM、cgroup、behavior/trace 和外部报告。
调用 CI 固定 harness 提交 SHA，记录实际 source/harness SHA、镜像 ID 和原始结果。
任何测试都必须使用指定源码提交编译出的 PHP 7.0.33，不使用系统 PHP。

## 入口

- `harness/Dockerfile`：共用工具链；支持 Debian 12、CentOS 7/8/Stream 9、UBI 9。
  CentOS 7/8 使用对应 Vault；Bison 3.5.1 和 RPM 的 re2c 3.0 校验 SHA256。
- `harness/build.sh debug|release|asan|legacy|baseline`：唯一构建入口；legacy/baseline 仅作隔离比较。
- `harness/platform.sh debug|release|asan`：构建后调用本项目 native/FPM 检查；
  ASan 额外验证系统分配器。PHP 源码内的 PHPT 和 VM 生成比较由 php-src 的 CI 随后执行。
- `harness/docker-memory-invariants.py --image IMAGE --install INSTALL --output NEW_DIR`：
  宿主调用 Docker，64/96/128MiB cgroup Zend OOM、kernel OOM 和 CLI kernel OOM 共 7 项；
  验证退出码、内核 OOM 计数、准确的 worker victim 和替换 worker 的 session 连续性。
- `run.py` / `trace-run.py` / `tools/report.py`：保留三构建行为、两构建插桩和报告接口。
  reporter 成功生成不等于测试通过；调用方必须同时检查 runner 状态和报告 pass。

构建容器约定：只读 `/input/source.tar`、只读 `/harness`、可写 `/work`；
源码 `/work/source`、安装 `/work/install`、日志 `/work/logs`。
编译与测试 `--network none`，仅镜像构建阶段下载依赖。
source/harness 检出到 workspace 的同级目录，结果放 runner temp，保持被测源码干净。

## 成本与证据边界

五种发行版跑 amd64 Debug/Release，另有 Debian arm64 Debug 和 amd64 ASan。
上述五种发行版 amd64 Debug/Release 执行 cgroup；不能用 skipped 代替覆盖。
容器验证发行版用户空间和工具链，共享宿主内核，不声称验证了原生 CentOS 内核。
三构建与 trace 集中在 Debian，避免在每个发行版重复五次构建。
PHPT/平台结果由调用 CI 分别保留；目前 HTML E2E 报告不合并平台矩阵，不宣称已包括它。

后续可将平台结果纳入统一报告、复用同源码/模式/工具链的构建产物、按工具链内容缓存镜像。
优化必须保留现有断言、失败退出状态与 SHA 可追溯性，不顺带修改 PHP 历史缺陷。

CLI 取证保留一个观察进程，PHP 子进程被 SIGKILL 后读取同一 cgroup 的 oom_kill 增量，
并要求没有 shutdown 标记；不把 137 或 Docker 的 OOMKilled 标志单独当作内核 OOM 证据。
Docker 状态仍原样记录。该设计避免最后进程退出后 cgroup 回收与异步 OOM 状态的取证窗口，
参见 [containerd 事件处理说明](https://github.com/containerd/containerd/blob/main/internal/cri/server/events.go)。
