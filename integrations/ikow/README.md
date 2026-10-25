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
