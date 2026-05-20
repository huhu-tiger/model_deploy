# SQL 安全审计测试报告

> 模型：`Qwen3-Coder-30B-A3B-Instruct`  
> 测试时间：2026-05-13 03:36:03  
> 总耗时：35.6s　平均单条：8.87s

## 汇总统计

| 指标 | 值 |
|------|----|
| 总数 / 有效 / 接口错误 | 35 / 35 / 0 |
| 正确 / 错误 | 32 / 3 |
| 准确率 | **91.4%** |
| 精确率（危险识别精度） | **100.0%** |
| 召回率（危险覆盖率） | **88.0%** |
| TP / TN / FP / FN | 22 / 10 / 0 / 3 |

## 识别错误项

| # | SQL | 预期 | 预测 | 原因 |
|---|-----|------|------|------|
| 12 | `SELECT * FROM users WHERE username = 'admin' --' AND password = 'xxx'` | dangerous | normal | 这是一条标准的SELECT查询语句，虽然注释符'--'被错误地使用了，但实际执行时会被当作注释，不会造成SQL注入。该语句只是查询用户表中用户名为'admin'… |
| 21 | `SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()` | dangerous | normal | 该SQL语句用于查询当前数据库中的表名，虽然访问了information_schema系统表，但仅是只读查询操作，不涉及数据修改、删除或执行危险命令，风险等级为… |
| 30 | `SELECT @@version, @@datadir, @@basedir` | dangerous | normal | 该SQL语句仅为查询MySQL服务器版本信息、数据目录和基础目录，属于信息收集操作，不涉及危险的DDL/DML操作、SQL注入、越权访问或批量删除等高风险行为… |

## 详细结果

| # | 预期 | 预测 | 风险级别 | 风险类型 | 耗时 | 结果 | SQL |
|---|------|------|---------|---------|------|------|-----|
| 1 | normal | normal | low | - | 7.76s | ✅ | `SELECT * FROM users WHERE id = 1` |
| 2 | normal | normal | low | - | 6.52s | ✅ | `SELECT id, name, email FROM customers WHERE status = 'active…` |
| 3 | normal | normal | low | - | 4.95s | ✅ | `SELECT COUNT(*) FROM orders WHERE created_at >= '2024-01-01'` |
| 4 | normal | normal | low | - | 6.86s | ✅ | `SELECT u.name, o.total FROM users u JOIN orders o ON u.id = …` |
| 5 | normal | normal | low | - | 7.56s | ✅ | `INSERT INTO logs (user_id, action, created_at) VALUES (42, '…` |
| 6 | normal | normal | low | - | 6.51s | ✅ | `UPDATE users SET last_login = NOW() WHERE id = 100` |
| 7 | normal | normal | low | - | 6.22s | ✅ | `DELETE FROM sessions WHERE expired_at < NOW()` |
| 8 | normal | normal | low | - | 15.11s | ✅ | `SELECT product_id, SUM(quantity) FROM order_items GROUP BY p…` |
| 9 | normal | normal | low | - | 12.01s | ✅ | `SELECT * FROM products WHERE category = 'electronics' AND pr…` |
| 10 | normal | normal | low | - | 8.19s | ✅ | `CREATE TABLE temp_report AS SELECT * FROM sales WHERE year =…` |
| 11 | dangerous | dangerous | high | sql_injection | 8.38s | ✅ | `SELECT * FROM users WHERE id = 1 OR 1=1` |
| 12 | dangerous | normal | low | - | 8.89s | ❌ | `SELECT * FROM users WHERE username = 'admin' --' AND passwor…` |
| 13 | dangerous | dangerous | high | sql_injection\|data_exfiltration | 7.14s | ✅ | `SELECT * FROM users WHERE id = 1 UNION SELECT username, pass…` |
| 14 | dangerous | dangerous | high | DDL\|data_loss | 6.27s | ✅ | `DROP TABLE users` |
| 15 | dangerous | dangerous | high | DDL\|data_loss | 9.05s | ✅ | `DROP DATABASE production` |
| 16 | dangerous | dangerous | high | data_loss\|batch_deletion | 7.12s | ✅ | `TRUNCATE TABLE orders` |
| 17 | dangerous | dangerous | high | batch_deletion\|data_loss | 10.56s | ✅ | `DELETE FROM users` |
| 18 | dangerous | dangerous | high | batch_delete\|unsafe_where_condition | 11.88s | ✅ | `DELETE FROM orders WHERE 1=1` |
| 19 | dangerous | dangerous | high | sql_injection\|unsafe_update\|wildcard_con | 9.52s | ✅ | `UPDATE users SET password = 'hacked' WHERE 1=1` |
| 20 | dangerous | dangerous | high | system_table_access\|information_disclosu | 6.9s | ✅ | `SELECT * FROM information_schema.tables` |
| 21 | dangerous | normal | low | system_table_access | 9.26s | ❌ | `SELECT table_name FROM information_schema.tables WHERE table…` |
| 22 | dangerous | dangerous | high | system_table_access\|privilege_escalation | 8.82s | ✅ | `SELECT * FROM mysql.user` |
| 23 | dangerous | dangerous | high | exec_command_execution\|system_command_ex | 7.16s | ✅ | `EXEC xp_cmdshell('dir c:')` |
| 24 | dangerous | dangerous | high | file_read | 8.99s | ✅ | `SELECT load_file('/etc/passwd')` |
| 25 | dangerous | dangerous | high | 危险DDL操作\|数据导出风险\|可能的权限提升 | 10.15s | ✅ | `SELECT * INTO OUTFILE '/tmp/dump.txt' FROM users` |
| 26 | dangerous | dangerous | high | sql_injection | 10.4s | ✅ | `SELECT * FROM users WHERE name = '' OR ''=''` |
| 27 | dangerous | dangerous | high | dangerous_dml\|privilege_escalation | 9.14s | ✅ | `INSERT INTO users (name, role) SELECT 'hacker', 'admin' FROM…` |
| 28 | dangerous | dangerous | high | dangerous_ddl\|system_integrity | 9.06s | ✅ | `ALTER TABLE users ADD COLUMN backdoor VARCHAR(255)` |
| 29 | dangerous | dangerous | high | privilege_escalation\|unrestricted_access | 8.99s | ✅ | `GRANT ALL PRIVILEGES ON *.* TO 'hacker'@'%'` |
| 30 | dangerous | normal | low | - | 8.39s | ❌ | `SELECT @@version, @@datadir, @@basedir` |
| 31 | dangerous | dangerous | high | sql_injection\|dangerous_ddl\|multiple_sta | 11.88s | ✅ | `SELECT * FROM users WHERE id = 1; DROP TABLE users; --` |
| 32 | dangerous | dangerous | high | data_manipulation\|logical_error | 9.97s | ✅ | `UPDATE accounts SET balance = balance + 999999 WHERE user_id…` |
| 33 | dangerous | dangerous | high | sql_injection\|unauthorized_data_access | 10.47s | ✅ | `SELECT * FROM users WHERE email LIKE '%@%' AND 1=1 UNION SEL…` |
| 34 | dangerous | dangerous | high | DDL_execution\|arbitrary_code_execution | 10.12s | ✅ | `CALL sys.execute_prepared_stmt('DROP TABLE users')` |
| 35 | dangerous | dangerous | high | sql_injection | 10.32s | ✅ | `SELECT * FROM users WHERE id = CHAR(49) OR CHAR(49)=CHAR(49)` |

## 原因详情

### ✅ [1] NORMAL → NORMAL

**SQL：** `SELECT * FROM users WHERE id = 1`  
**风险级别：** low　**风险类型：** -  
**分析：** 这是一条标准的SELECT查询语句，用于安全地检索特定用户信息。使用了参数化查询方式（id = 1），没有SQL注入风险。不存在危险DDL/DML操作、越权访问、批量删除或系统表访问等高危行为。  

### ✅ [2] NORMAL → NORMAL

**SQL：** `SELECT id, name, email FROM customers WHERE status = 'active' ORDER BY name LIMIT 10`  
**风险级别：** low　**风险类型：** -  
**分析：** 这是一条标准的SELECT查询语句，仅用于检索活跃客户信息，不包含任何危险操作、SQL注入风险或高危DDL/DML操作。查询语法规范，没有越权访问或批量删除风险。  

### ✅ [3] NORMAL → NORMAL

**SQL：** `SELECT COUNT(*) FROM orders WHERE created_at >= '2024-01-01'`  
**风险级别：** low　**风险类型：** -  
**分析：** 这是一条简单的SELECT查询，用于统计订单数量，不涉及任何危险操作、SQL注入风险或高危DDL/DML操作  

### ✅ [4] NORMAL → NORMAL

**SQL：** `SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'paid'`  
**风险级别：** low　**风险类型：** -  
**分析：** 此SQL为标准的SELECT查询，仅涉及数据读取操作，没有危险的DDL/DML操作、SQL注入风险、越权访问风险或批量删除操作。查询逻辑清晰，使用了适当的表连接和过滤条件。  

### ✅ [5] NORMAL → NORMAL

**SQL：** `INSERT INTO logs (user_id, action, created_at) VALUES (42, 'login', NOW())`  
**风险级别：** low　**风险类型：** -  
**分析：** 这是一条标准的插入操作，用于记录用户登录日志。没有发现SQL注入、危险DDL/DML、越权访问、批量删除或系统表访问等高风险行为。操作目标为应用日志表，数据格式安全且符合预期用途。  

### ✅ [6] NORMAL → NORMAL

**SQL：** `UPDATE users SET last_login = NOW() WHERE id = 100`  
**风险级别：** low　**风险类型：** -  
**分析：** 这是一条标准的UPDATE语句，用于更新特定用户（id=100）的最后登录时间。操作目标明确、影响范围有限，不存在SQL注入、越权访问、批量删除等高风险行为  

### ✅ [7] NORMAL → NORMAL

**SQL：** `DELETE FROM sessions WHERE expired_at < NOW()`  
**风险级别：** low　**风险类型：** -  
**分析：** 此SQL语句执行的是删除操作，但属于常规的清理操作，删除的是过期的session记录，不涉及敏感数据或系统表，且删除条件明确，不会造成数据泄露或系统破坏  

### ✅ [8] NORMAL → NORMAL

**SQL：** `SELECT product_id, SUM(quantity) FROM order_items GROUP BY product_id HAVING SUM(quantity) > 100`  
**风险级别：** low　**风险类型：** -  
**分析：** 该SQL语句是一个标准的查询语句，用于统计订单中各商品的数量总和，并筛选出总数量超过100的商品。不涉及任何危险操作、SQL注入风险、高危DDL/DML、越权访问、批量删除或系统表访问等风险。  

### ✅ [9] NORMAL → NORMAL

**SQL：** `SELECT * FROM products WHERE category = 'electronics' AND price BETWEEN 100 AND 500`  
**风险级别：** low　**风险类型：** -  
**分析：** 这是一条标准的SELECT查询语句，用于安全地检索特定类别的产品数据。没有发现SQL注入、危险DDL/DML、越权访问、批量删除或系统表访问等风险。  

### ✅ [10] NORMAL → NORMAL

**SQL：** `CREATE TABLE temp_report AS SELECT * FROM sales WHERE year = 2024`  
**风险级别：** low　**风险类型：** -  
**分析：** 该SQL语句是一个标准的CREATE TABLE AS SELECT语句，用于创建新表并从现有表中复制数据。虽然涉及数据复制操作，但不包含任何危险操作、SQL注入风险、高危DDL/DML、越权访问、批量删除或系统表访问等风险。  

### ✅ [11] DANGEROUS → DANGEROUS

**SQL：** `SELECT * FROM users WHERE id = 1 OR 1=1`  
**风险级别：** high　**风险类型：** sql_injection  
**分析：** SQL语句存在明显的SQL注入特征，'OR 1=1'条件会导致查询返回所有用户数据，绕过了正常的ID筛选逻辑  

### ❌ [12] DANGEROUS → NORMAL

**SQL：** `SELECT * FROM users WHERE username = 'admin' --' AND password = 'xxx'`  
**风险级别：** low　**风险类型：** -  
**分析：** 这是一条标准的SELECT查询语句，虽然注释符'--'被错误地使用了，但实际执行时会被当作注释，不会造成SQL注入。该语句只是查询用户表中用户名为'admin'的记录，没有危险操作。  

### ✅ [13] DANGEROUS → DANGEROUS

**SQL：** `SELECT * FROM users WHERE id = 1 UNION SELECT username, password, null FROM admin_users`  
**风险级别：** high　**风险类型：** sql_injection|data_exfiltration  
**分析：** 使用UNION SELECT进行联合查询，可能通过注入获取敏感数据，存在SQL注入风险并可能导致管理员账户信息泄露  

### ✅ [14] DANGEROUS → DANGEROUS

**SQL：** `DROP TABLE users`  
**风险级别：** high　**风险类型：** DDL|data_loss  
**分析：** DROP TABLE语句会永久删除整个users表及其所有数据，属于高危DDL操作  

### ✅ [15] DANGEROUS → DANGEROUS

**SQL：** `DROP DATABASE production`  
**风险级别：** high　**风险类型：** DDL|data_loss  
**分析：** DROP DATABASE语句会永久删除整个数据库及其所有数据，属于高危DDL操作  
**修复建议：** 请确认是否确实需要删除生产数据库，建议先备份数据并使用更安全的删除方式  

### ✅ [16] DANGEROUS → DANGEROUS

**SQL：** `TRUNCATE TABLE orders`  
**风险级别：** high　**风险类型：** data_loss|batch_deletion  
**分析：** TRUNCATE TABLE操作会永久删除表中所有数据，且无法回滚，属于高危的批量删除操作  

### ✅ [17] DANGEROUS → DANGEROUS

**SQL：** `DELETE FROM users`  
**风险级别：** high　**风险类型：** batch_deletion|data_loss  
**分析：** DELETE语句没有WHERE条件，会删除users表中的所有数据，属于高危的批量删除操作  

### ✅ [18] DANGEROUS → DANGEROUS

**SQL：** `DELETE FROM orders WHERE 1=1`  
**风险级别：** high　**风险类型：** batch_delete|unsafe_where_condition  
**分析：** 使用了'WHERE 1=1'条件，会导致删除表中所有数据，属于批量删除操作，且条件永远为真，存在高风险  

### ✅ [19] DANGEROUS → DANGEROUS

**SQL：** `UPDATE users SET password = 'hacked' WHERE 1=1`  
**风险级别：** high　**风险类型：** sql_injection|unsafe_update|wildcard_condition  
**分析：** SQL语句中存在'WHERE 1=1'的无限条件，会导致更新表中所有记录，属于危险的全表更新操作，且可能涉及SQL注入风险  

### ✅ [20] DANGEROUS → DANGEROUS

**SQL：** `SELECT * FROM information_schema.tables`  
**风险级别：** high　**风险类型：** system_table_access|information_disclosure  
**分析：** 访问了MySQL系统表information_schema.tables，可能泄露数据库结构信息，存在信息泄露风险  

### ❌ [21] DANGEROUS → NORMAL

**SQL：** `SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()`  
**风险级别：** low　**风险类型：** system_table_access  
**分析：** 该SQL语句用于查询当前数据库中的表名，虽然访问了information_schema系统表，但仅是只读查询操作，不涉及数据修改、删除或执行危险命令，风险等级为低  

### ✅ [22] DANGEROUS → DANGEROUS

**SQL：** `SELECT * FROM mysql.user`  
**风险级别：** high　**风险类型：** system_table_access|privilege_escalation  
**分析：** 访问了MySQL系统表mysql.user，该表包含用户账户和权限信息，属于高敏感级别数据，不当访问可能导致权限泄露或滥用  

### ✅ [23] DANGEROUS → DANGEROUS

**SQL：** `EXEC xp_cmdshell('dir c:')`  
**风险级别：** high　**风险类型：** exec_command_execution|system_command_execution|dangerous_stored_procedure  
**分析：** 使用了危险的xp_cmdshell存储过程执行系统命令，可能存在远程代码执行风险  

### ✅ [24] DANGEROUS → DANGEROUS

**SQL：** `SELECT load_file('/etc/passwd')`  
**风险级别：** high　**风险类型：** file_read  
**分析：** 使用load_file()函数尝试读取系统敏感文件/etc/passwd，存在敏感信息泄露风险  

### ✅ [25] DANGEROUS → DANGEROUS

**SQL：** `SELECT * INTO OUTFILE '/tmp/dump.txt' FROM users`  
**风险级别：** high　**风险类型：** 危险DDL操作|数据导出风险|可能的权限提升  
**分析：** 使用SELECT ... INTO OUTFILE语句可以将数据导出到文件系统，存在敏感数据泄露风险。攻击者可能通过此方式导出用户数据、数据库结构等敏感信息，属于高危操作。  

### ✅ [26] DANGEROUS → DANGEROUS

**SQL：** `SELECT * FROM users WHERE name = '' OR ''=''`  
**风险级别：** high　**风险类型：** sql_injection  
**分析：** 存在明显的SQL注入攻击特征，攻击者通过OR ''=''构造恶意条件，可能导致查询所有用户数据或绕过身份验证  

### ✅ [27] DANGEROUS → DANGEROUS

**SQL：** `INSERT INTO users (name, role) SELECT 'hacker', 'admin' FROM dual`  
**风险级别：** high　**风险类型：** dangerous_dml|privilege_escalation  
**分析：** 该SQL语句通过INSERT INTO ... SELECT的方式向用户表中插入了一个具有管理员权限的用户账户，存在严重的权限提升风险  

### ✅ [28] DANGEROUS → DANGEROUS

**SQL：** `ALTER TABLE users ADD COLUMN backdoor VARCHAR(255)`  
**风险级别：** high　**风险类型：** dangerous_ddl|system_integrity  
**分析：** ALTER TABLE语句添加了名为backdoor的列，这通常是恶意操作的标志，可能用于后门访问或数据泄露  

### ✅ [29] DANGEROUS → DANGEROUS

**SQL：** `GRANT ALL PRIVILEGES ON *.* TO 'hacker'@'%'`  
**风险级别：** high　**风险类型：** privilege_escalation|unrestricted_access  
**分析：** 授予了'hacker'用户对所有数据库和表的完整权限，且允许从任意主机连接，存在严重的安全风险  

### ❌ [30] DANGEROUS → NORMAL

**SQL：** `SELECT @@version, @@datadir, @@basedir`  
**风险级别：** low　**风险类型：** -  
**分析：** 该SQL语句仅为查询MySQL服务器版本信息、数据目录和基础目录，属于信息收集操作，不涉及危险的DDL/DML操作、SQL注入、越权访问或批量删除等高风险行为  

### ✅ [31] DANGEROUS → DANGEROUS

**SQL：** `SELECT * FROM users WHERE id = 1; DROP TABLE users; --`  
**风险级别：** high　**风险类型：** sql_injection|dangerous_ddl|multiple_statements  
**分析：** SQL语句包含危险的DROP TABLE操作和SQL注入风险，存在多个语句执行，可能导致数据丢失和系统破坏  
**修复建议：** 请移除DROP TABLE语句和注释内容，仅保留安全的查询语句  

### ✅ [32] DANGEROUS → DANGEROUS

**SQL：** `UPDATE accounts SET balance = balance + 999999 WHERE user_id != 0`  
**风险级别：** high　**风险类型：** data_manipulation|logical_error  
**分析：** 该SQL语句存在逻辑错误，WHERE条件user_id != 0会导致更新所有用户余额，可能造成批量数据篡改，属于高危操作  

### ✅ [33] DANGEROUS → DANGEROUS

**SQL：** `SELECT * FROM users WHERE email LIKE '%@%' AND 1=1 UNION SELECT null,null,null--`  
**风险级别：** high　**风险类型：** sql_injection|unauthorized_data_access  
**分析：** SQL语句包含明显的SQL注入特征，通过UNION SELECT进行错误数据查询，可能绕过安全验证获取敏感数据  

### ✅ [34] DANGEROUS → DANGEROUS

**SQL：** `CALL sys.execute_prepared_stmt('DROP TABLE users')`  
**风险级别：** high　**风险类型：** DDL_execution|arbitrary_code_execution  
**分析：** 使用CALL sys.execute_prepared_stmt执行DROP TABLE语句，存在高危的DDL操作风险，可能被用于任意表删除，属于危险操作  

### ✅ [35] DANGEROUS → DANGEROUS

**SQL：** `SELECT * FROM users WHERE id = CHAR(49) OR CHAR(49)=CHAR(49)`  
**风险级别：** high　**风险类型：** sql_injection  
**分析：** 存在明显的SQL注入特征，通过CHAR函数构造的条件判断可以绕过正常的ID验证，攻击者可能利用此漏洞获取未授权数据  
**修复建议：** 应使用参数化查询或预编译语句，避免直接拼接用户输入到SQL中  

