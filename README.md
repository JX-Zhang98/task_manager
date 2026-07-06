# Quadrant Task Manager

一个基于 PyQt6 的四象限任务管理器。项目来自 Gemini 分享页中的设计讨论整理，已合并为一套完整、可运行、可继续维护的代码结构。

## 功能

- 收件箱与四象限视图
- 任务自动排序：未完成任务优先，再按手动位置（sort_order）排序，截止时间仅作为同位置任务的次级排序
- 拖拽任务到不同象限
- 任务标题、描述、截止时间、具体时间和提醒
- 完成状态复选框，已完成任务当天仍显示，历史完成任务进入归档
- 归档窗口可查看和恢复完成任务
- 统一样式配置，右键菜单悬停不会丢失文字
- 多语言文字托管，当前默认中文
- 自定义 SVG Logo 与复选框资源

## 运行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

任务数据会保存在 `data/tasks.json`，该文件已被 `.gitignore` 忽略。

归档口径：归档窗口展示“历史完成记录”，即不包含今天刚完成、仍保留在主视图里的任务。

## CLI

命令行入口统一输出 JSON，默认读写 `data/tasks.json`，写命令会记录审计日志到同目录的 `audit.log.jsonl`。

全局参数：

```bash
python -m app.cli --file data/tasks.json --pretty <command>
python -m app.cli --file data/tasks.json --audit-file data/audit.log.jsonl <command>
python -m app.cli --source cli --request-id req-1 --actor user <command>
```

查询任务：

```bash
python -m app.cli list --view all
python -m app.cli list --view inbox
python -m app.cli list --view matrix
python -m app.cli list --view archive
python -m app.cli list --tag Work
python -m app.cli get <task-id>
```

管理任务：

```bash
python -m app.cli add "写周报" --description "整理本周进展" --quadrant q1
python -m app.cli add "写周报" --tag Work --tag Weekly
python -m app.cli update <task-id> --title "更新标题" --clear-due-date
python -m app.cli move <task-id> q2
python -m app.cli complete <task-id>
python -m app.cli reopen <task-id>
python -m app.cli delete <task-id> --dry-run
python -m app.cli delete <task-id> --confirm
```

时间和提醒：

```bash
python -m app.cli add "开会" --due-date 2026-06-09T09:30 --has-time --reminder-minutes 15
python -m app.cli check-reminders --now 2026-06-09T09:15:00
```

标签：

```bash
python -m app.cli tags
python -m app.cli add "处理合同" --tag Work --tag Legal
python -m app.cli list --tag Legal
python -m app.cli tag-rename "Work" "Deep Work" --color "#7C3AED" --confirm
python -m app.cli tag-delete "OldTag" --confirm
python -m app.cli tag-merge "SourceTag" "TargetTag" --confirm
python -m app.cli tag-prune --cutoff-days 90 --confirm
```

`tags` 会列出所有标签及引用任务数量；`add --tag` 可重复使用，已有标签会复用原颜色，新标签会自动分配颜色。

标签管理命令（tag-rename、tag-delete、tag-merge、tag-prune）属于破坏性操作，必须使用 `--confirm` 确认或 `--dry-run` 预演：

```bash
python -m app.cli tag-delete "OldTag" --dry-run
python -m app.cli tag-prune --dry-run
```

安全预演：

```bash
python -m app.cli add "预演任务" --dry-run
python -m app.cli --source future_ai delete <task-id> --dry-run
```

## 测试

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

UI smoke test 使用 Qt offscreen 模式，不会打开真实窗口。

## 打包

```powershell
pip install -r requirements-build.txt
.\scripts\build_exe.ps1
```

产物会输出到 `outputs/TaskManager-v0.1.0-win64.zip`。

## 结构

```text
app/
  config.py
  domain/
    task_rules.py
  models/
    task.py
  resources/
    strings.py
    imgs/
  services/
    task_service.py
  ui/
    components/
    views/
main.py
docs/
  gemini-summary.md
```

## 语言切换

在 `app/config.py` 中修改：

```python
LANGUAGE = "cn"
```

可选值为 `"cn"` 或 `"en"`。
