# ikow 研究与检测规则接入

固定上游：[`31519e6d`](https://github.com/ikow/php2shell-poc/tree/31519e6d8a84dee1df1262961ed1bebb65accadd)。按 MIT 原样引入 LICENSE 和 detection/ 四份规则文件，文件摘要见 source.json。不自动更新，不导入或运行命令执行利用链。

```sh
python3 integrations/ikow/run.py --output artifacts/ikow-unit-001 --lua lua
```

此入口使用真实 Lua 解释器执行未经修改的 upstream/php2shell.lua，但 ngx API 是测试替身、输入为无害合成字符串。6 项单元检查验证普通上传、progress 阻断、PHPSESSID 告警、PHP 文本签名、log-only、非 POST 跳过。它不等于 OpenResty 部署验证，更不等于 PHP 修复或 RCE 全链通过。

Suricata、Sigma、ModSecurity 文件目前只固定版本保存，状态为 IMPORTED / NOT RUN。它们尚未通过对应引擎的语法及流量验证；上游注释中的严重性判断也不作为本工具的漏洞结论。规则命中可能存在误报与漏报，不能直接用命中代替可利用性证明，也不能用未命中证明安全。

| 上游链 | 当前接入深度 |
|---|---|
| A / session + LFI | 现有 progress 门禁只验证前置路径；完整链 NOT RUN |
| B / var_destroy UAF | NOT RUN |
| C / handler mismatch | NOT RUN |
| D / mod_php OOM | 当前 php70 套件不覆盖 mod_php；NOT RUN |
| E / FPM stale state | 现有 OOM/session 门禁验证部分行为；完整链 NOT RUN |

PHP 修复验证、上游攻击链、规则单元检查和真实检测引擎必须独立计分。未来增加引擎流量回放时，应另存引擎版本、请求/响应/日志证据及预期命中 rule ID，不能把本文的规则导入升级为已执行覆盖。

## 真实 OpenResty HTTP 回放

```sh
docker pull openresty/openresty:alpine-fat
python3 integrations/ikow/openresty-run.py --output artifacts/ikow-openresty-001
```

这与前面的 Lua 单元检查是不同证据：使用真实 OpenResty worker 与 curl 请求，记录 HTTP 状态、响应、access/error 日志、版本与镜像 ID。容器只读、无网络、无 capabilities、非 root、仅使用容器内部 loopback，不接收外部目标地址；结束后回收自己创建的唯一命名容器。

当前本地实跑 6 项通过：普通 multipart 放行、progress 阻断、PHPSESSID 仅告警、PHP 文本签名阻断、log-only 放行、GET 跳过。请求是无害合成 fixture，后端只有固定响应标记，没有 PHP 应用，不执行任何利用链。通过只能证明这些 fixture 上的真实检测引擎行为，不表示通用检测覆盖或 PHP 修复通过。

`tools/report.py --detection <unit-output> --engine <openresty-output>` 将两类检测与 PHP 断言分别呈现；Suricata/Sigma/ModSecurity 仍未执行。CI 的 OpenResty 回放在原 PHP 测试之外独立运行，并记录本次实际引擎版本。
