# ChatPD 服务器 Agent 数据同步与部署 Runbook（初稿）

本文档用于指导服务器上的 Cursor Agent 在代码合并后，完成数据同步、数据库转换、服务重启与验收。

适用目录（服务器）：
- `/root/web_app/web_chatpd`

---

## 1. 结论先行（最小数据同步集）

在**服务运行期**（网页查询/API 正常工作）场景下，最小必需数据是：
- `data/chatpd_data.db`（必需）

`data/final_product/ChatPD_WebData_from_db.json` 的作用：
- 主要用于离线脚本 `python3 -m src.json2db` 生成/刷新数据库；
- 在运行期仅用于 `/api/data-status` 显示源 JSON 元信息（存在性、大小、修改时间）；
- 缺失不会直接让核心查询 API 挂掉，但会影响状态面板显示，并且无法按默认流程重新转库。

因此：
- 如果你只想“跑服务”，且数据库已是最新：可只同步 `data/chatpd_data.db`。
- 如果你还要在服务器执行“JSON -> DB 转换”：必须同步 `data/final_product/ChatPD_WebData_from_db.json`（或通过 `CHATPD_JSON_FILE` 指定其它源 JSON）。

---

## 2. 为什么不是只同步 JSON

后端查询读的是 SQLite，不是直接读 JSON：
- `src/web_app/search_engine.py` 使用 `data/chatpd_data.db` 创建连接池；
- `src/web_app/query_service.py` 的 `DB_PATH` 也是 `data/chatpd_data.db`；
- 各核心 API（`/api/query`、`/api/search`、`/api/paper/...`、`/api/dataset/...`）都基于数据库查询。

JSON 读取点仅两类：
- `src/json2db.py`：离线导入脚本读取 JSON 并重建数据库；
- `src/web_app/search_engine.py`：`/api/data-status` 读取 JSON 文件元信息（不解析内容）。

---

## 3. 推荐的服务器执行流程（给 Agent）

以下步骤默认在服务器目录 `/root/web_app/web_chatpd` 执行。

### Step A. 代码更新与合并

1) 拉取并合并代码（按你的分支策略执行）。
2) 确认当前目录正确：
- `pwd`
- `git status`

### Step B. 同步关键数据（你手工同步）

按目标选择其一：

- 方案 1：仅更新数据库（最快上线）
  - 同步：`data/chatpd_data.db`
  - 不执行转库，直接重启服务验收。

- 方案 2：更新 JSON 并在服务器转库（推荐可追溯）
  - 同步：`data/final_product/ChatPD_WebData_from_db.json`
  - 然后执行 `python3 -m src.json2db` 生成新的 `data/chatpd_data.db`
  - 再重启服务验收。

### Step C. 服务器上做转库（仅方案 2 需要）

```bash
cd /root/web_app/web_chatpd
python3 -m src.json2db
```

若要使用非默认 JSON 路径：

```bash
cd /root/web_app/web_chatpd
CHATPD_JSON_FILE=data/final_product/YourFile.json python3 -m src.json2db
```

### Step D. 重启服务

优先 systemd：

```bash
cd /root/web_app/web_chatpd
systemctl restart chatpd.service
systemctl status chatpd.service --no-pager -l
```

若当前环境不用 systemd，改用脚本：

```bash
cd /root/web_app/web_chatpd
bash start_chatpd.sh restart
```

---

## 4. 验收清单（必须执行）

### 4.1 文件与数据基础检查

```bash
cd /root/web_app/web_chatpd
ls -lh data/chatpd_data.db
sqlite3 data/chatpd_data.db "SELECT COUNT(*) FROM dataset_usage;"
```

期望：
- 数据库文件存在且大小合理；
- 记录数 > 0。

### 4.2 API 健康检查

```bash
curl -s "http://127.0.0.1:5000/api/filters" | head
curl -s "http://127.0.0.1:5000/api/query?q=dataset&page=1&per_page=5" | head
curl -s "http://127.0.0.1:5000/api/data-status" | head
```

期望：
- `/api/filters` 返回包含聚合字段；
- `/api/query` 返回结果结构（`results`、`total_pages` 等）；
- `/api/data-status` 中 `database_exists` 为 `true`。

---

## 5. 失败处理与回滚建议

### 常见失败 1：服务启动后查询为空/报错

排查顺序：
1) `data/chatpd_data.db` 是否存在且非空；
2) `dataset_usage` 是否有记录；
3) `journalctl -u chatpd.service -n 200 --no-pager` 看数据库错误；
4) 若刚转库，重新执行 `python3 -m src.json2db` 并重启。

### 常见失败 2：JSON 存在但转库失败

排查：
1) JSON 是否是合法 UTF-8/合法 JSON；
2) 字段结构是否符合 `src/json2db.py` 预期；
3) 用 `CHATPD_JSON_FILE` 指向正确文件重试。

### 回滚建议

在更新前备份数据库：

```bash
cd /root/web_app/web_chatpd
cp data/chatpd_data.db "data/chatpd_data.db.bak.$(date +%Y%m%d_%H%M%S)"
```

若新库异常，恢复备份并重启服务。

---

## 6. 给服务器 Agent 的简版执行指令

可直接交给服务器 Agent 的任务描述：

1) 在 `/root/web_app/web_chatpd` 拉取并合并最新代码；
2) 等待人工同步关键数据（至少 `data/chatpd_data.db`，若需转库则同步 `data/final_product/ChatPD_WebData_from_db.json`）；
3) 如果要求转库，执行 `python3 -m src.json2db`；
4) 重启 `chatpd.service` 并检查状态；
5) 执行 3 个 API 验收请求并回传结果摘要；
6) 若失败，回传日志与建议，不做破坏性操作。

---

## 7. 一句话策略建议

你当前“手工同步关键数据”的策略可行，推荐优先同步 `data/chatpd_data.db` 以降低上线复杂度；仅在确实需要服务器侧重建数据库时，再同步 `data/final_product/ChatPD_WebData_from_db.json` 并执行转库。
