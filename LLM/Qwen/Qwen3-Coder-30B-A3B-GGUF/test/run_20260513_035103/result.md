# SQL 安全审计测试报告

> 模型：`Qwen3-Coder-30B-A3B-Instruct`  
> 测试时间：2026-05-13 03:52:36  
> 总耗时：93.6s　平均单条：9.54s

## 汇总统计

| 指标 | 值 |
|------|----|
| 总数 / 有效 / 接口错误 | 96 / 96 / 0 |
| JSON 结构合法率 | **100.0%** (96/96) |
| 正确 / 错误 | 91 / 5 |
| 准确率 | **94.8%** |
| 精确率（危险识别精度） | **98.1%** |
| 召回率（危险覆盖率） | **96.4%** |
| TP / TN / FP / FN | 53 / 38 / 1 / 2 |

## 按类型统计

| 类型 | 总数 | 正确 | 准确率 |
|------|------|------|--------|
| `chat` | 15 | 15 | **100.0%** |
| `code` | 23 | 21 | **91.3%** |
| `shell` | 23 | 22 | **95.7%** |
| `sql` | 35 | 33 | **94.3%** |

## 按子类型统计

| 类型/子类型 | 总数 | 正确 | 准确率 |
|-----------|------|------|--------|
| `chat/code_question` | 1 | 1 | **100.0%** |
| `chat/creative` | 2 | 2 | **100.0%** |
| `chat/explain_code` | 2 | 2 | **100.0%** |
| `chat/factual` | 5 | 5 | **100.0%** |
| `chat/greeting` | 2 | 2 | **100.0%** |
| `chat/sql_question` | 1 | 1 | **100.0%** |
| `chat/summarize` | 1 | 1 | **100.0%** |
| `chat/translate` | 1 | 1 | **100.0%** |
| `code/base64_obfuscation` | 2 | 2 | **100.0%** |
| `code/crontab_backdoor` | 2 | 1 | **50.0%** ⚠️ |
| `code/file_destroy` | 2 | 2 | **100.0%** |
| `code/file_permission` | 2 | 2 | **100.0%** |
| `code/malicious_download` | 2 | 2 | **100.0%** |
| `code/memory_injection` | 2 | 2 | **100.0%** |
| `code/normal` | 8 | 7 | **87.5%** |
| `code/reverse_shell` | 3 | 3 | **100.0%** |
| `shell/crontab_backdoor` | 1 | 1 | **100.0%** |
| `shell/disk_dump` | 2 | 2 | **100.0%** |
| `shell/file_destroy` | 1 | 1 | **100.0%** |
| `shell/firewall_clear` | 2 | 2 | **100.0%** |
| `shell/malicious_download` | 3 | 3 | **100.0%** |
| `shell/nc_exfiltration` | 3 | 3 | **100.0%** |
| `shell/normal` | 6 | 6 | **100.0%** |
| `shell/privilege_escalation` | 1 | 1 | **100.0%** |
| `shell/reverse_shell` | 2 | 1 | **50.0%** ⚠️ |
| `shell/sudo_backdoor` | 2 | 2 | **100.0%** |
| `sql/batch_delete` | 2 | 2 | **100.0%** |
| `sql/batch_update` | 2 | 2 | **100.0%** |
| `sql/command_exec` | 2 | 2 | **100.0%** |
| `sql/dangerous_ddl` | 4 | 4 | **100.0%** |
| `sql/file_access` | 2 | 2 | **100.0%** |
| `sql/info_gathering` | 1 | 0 | **0.0%** ⚠️ |
| `sql/normal_ddl` | 1 | 1 | **100.0%** |
| `sql/normal_dml` | 3 | 3 | **100.0%** |
| `sql/normal_select` | 6 | 6 | **100.0%** |
| `sql/privilege_escalation` | 2 | 2 | **100.0%** |
| `sql/sql_injection` | 7 | 7 | **100.0%** |
| `sql/system_table` | 3 | 2 | **66.7%** ⚠️ |

## 识别错误项

| # | SQL | 预期 | 预测 | 原因 |
|---|-----|------|------|------|
