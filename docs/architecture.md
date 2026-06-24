# TaskManager Architecture

当前代码按"规则、用例、存储、适配、界面"分层。目标是让 PyQt UI、未来 CLI、未来 AI Skill、未来 MCP server 都通过同一组任务能力入口工作。

## 分层

- `app/domain/`
  - 纯业务规则：排序、过滤、归档、提醒触发判断、象限业务定义、标签规范化（`normalize_tags`）。
  - 不读写文件，不依赖 PyQt。
- `app/application/`
  - 应用用例层：`Command`、`CommandResult`、`TaskApplication.dispatch()`、应用事件。
  - 所有修改任务或标签的行为都必须通过 command 进入。
  - 不依赖 PyQt，不依赖任何 AI SDK。
- `app/infrastructure/`
  - 持久化适配层：`JsonTaskRepository`（任务）、`JsonTagCatalogRepository`（标签目录）。
  - 负责兼容 `data/tasks.json` 和 `data/tags.json` 的现有格式。
- `app/services/task_service.py`
  - PyQt 适配层。
  - 把 UI 方法转换为 command，并把 application event 转为 Qt signal。
  - 不承载业务逻辑和持久化。
- `app/ui/`
  - 只负责展示和用户交互。
  - 通过 `TaskService` 调用任务能力，不直接修改数据。
- Future CLI / Future AI / Future MCP
  - 后续都应调用 command/application 接口。
  - 不允许直接编辑 `data/tasks.json` 或 `data/tags.json`。

## 数据流

```text
UI / CLI / Future AI / Future MCP
-> Command
-> TaskApplication.dispatch()
-> Repository + Domain Rules
-> EventBus
-> TaskService / Qt signal
-> UI refresh
```

## 写操作入口

当前支持的 command：

### 任务 command

- `AddTask`
- `UpdateTask`
- `DeleteTask`
- `MoveTask`
- `CompleteTask`
- `ReopenTask`
- `CheckReminders`

### 标签 command

- `RenameTag(old_name, new_name, color)`
- `DeleteTag(name)`
- `MergeTag(source_name, target_name, target_color)`
- `PruneStaleTags(cutoff_days=90)` — 默认清理 90 天前的过期标签

执行 command 时可以传入 `CommandContext`：

```python
CommandContext(
    source="cli",
    dry_run=False,
    request_id=None,
    actor=None,
)
```

`source` 当前建议使用 `ui`、`cli`、`future_ai`、`test`。未来 AI 调用删除类能力时必须先使用
`dry_run=True` 取得 preview。

所有 command 都返回 `CommandResult`：

- `ok`
- `message`
- `changed`
- `would_change`
- `task_id`
- `preview`
- `data`
- `events`

## 事件

- `TaskChanged`
  - 任务新增、更新、删除、移动、完成、重开、提醒状态更新、标签操作时产生。
  - `action` 字段区分操作类型：`add`、`update`、`delete`、`move`、`complete`、`reopen`、`check_reminders`、`rename_tag`、`delete_tag`、`merge_tag`、`prune_stale_tags`。
- `ReminderTriggered`
  - 到达提醒触发时间时产生。

`TaskService` 会订阅这些事件，并转换成现有 UI 使用的 `data_changed` 和 `reminder_triggered`。

## 排序规则

排序键 `task_sort_key` 的优先级：

1. **完成状态** `task.completed` — 未完成优先
2. **手动位置** `task.sort_order` — 主排序键，反映拖拽排列顺序
3. **截止日期存在** `task.due_date is None` — 有截止日期的优先
4. **截止日期早晚** `task.due_date` — 同位置中截止日期早的优先

`sort_order` 是拖拽排序的存储方式，是除完成状态之外最重要的排序维度。`due_date` 仅在 `sort_order` 相同时作为次级排序条件。

## 存储

`JsonTaskRepository` 保持现有 JSON 格式：

```json
{
  "task-id": {
    "id": "task-id",
    "title": "Example"
  }
}
```

兼容旧数据：如果 payload 内缺少 `id`，会使用 JSON 外层 key 作为 fallback id。

`JsonTagCatalogRepository` 管理 `tags.json`：

```json
[
  {"name": "Work", "color": "#2563EB"},
  {"name": "Home", "color": "#059669"}
]
```

标签目录在加载和保存时均通过 `task_rules.normalize_tags` 进行规范化。

## 边界约束

- `domain`、`application`、`infrastructure` 不允许依赖 PyQt。
- AI 后续只能通过 command、CLI 或 MCP 调用任务能力。
- AI 不允许直接写 `data/tasks.json`。
- 标签操作必须通过 command 进入，不允许 UI 或 CLI 直接读写 `tags.json`。
- 标签规范化统一由 `app/domain/task_rules.normalize_tags` 处理。
- 当前版本不实现 MCP server，不引入模型 SDK，不发起网络请求。

## CLI

当前已有轻量 CLI 入口：

```bash
python -m app.cli --file data/tasks.json list --view inbox
python -m app.cli --file data/tasks.json add "写周报" --quadrant q1
python -m app.cli --file data/tasks.json delete <task-id> --dry-run
python -m app.cli --file data/tasks.json delete <task-id> --confirm
```

标签管理 CLI：

```bash
python -m app.cli tag-rename "Work" "Deep Work" --color "#7C3AED" --confirm
python -m app.cli tag-delete "OldTag" --confirm
python -m app.cli tag-merge "SourceTag" "TargetTag" --confirm
python -m app.cli tag-prune --cutoff-days 90 --confirm

# 预演模式
python -m app.cli tag-delete "OldTag" --dry-run
python -m app.cli tag-prune --dry-run
```

CLI 只做参数解析和 JSON 输出，写操作仍然会构造 command 并调用
`TaskApplication.dispatch()`。这层可以作为未来 AI/Skill/MCP 的稳定外壳，但当前不包含任何
AI 调用逻辑。

## Audit Log

UI 和 CLI 执行 command 后会追加 JSONL 审计记录，默认位置：

```text
data/audit.log.jsonl
```

每行包含：

- command 类型和 payload
- source / dry_run / request_id / actor
- ok / changed / would_change / task_id
- preview 和 events

审计日志用于追溯未来 AI 或自动化执行过什么。它不是业务数据源，任务数据仍然只由 repository
读写 `tasks.json`，标签目录数据仍然只由 `JsonTagCatalogRepository` 读写 `tags.json`。
