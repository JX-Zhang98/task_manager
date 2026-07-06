# Description Markdown Support Plan

## Context

Task descriptions currently only support plain text — stored as `str`, rendered via `QLabel` in hover popup, edited via `QTextEdit.setPlainText/toPlainText`. The goal is to support Markdown formatting (headings, bold, italic, lists, links, images) so descriptions can carry richer information.

User decisions:
- **编辑方式**：所见即所得（QTextEdit 用 `setMarkdown` 渲染），不分栏
- **图片存储**：本地目录 `data/images/`，描述中用相对路径 `![](images/abc.png)`
- **图片插入**：辅助按钮 + 支持剪贴板粘贴截图
- **卡片弹窗**：渲染 markdown，最多显示 10 行，宽度不变（300px）
- **不影响编辑框大小**

## EXE 兼容性

`config.py` 中 `APP_ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else BASE_DIR`，`DATA_DIR = APP_ROOT / "data"`。当用户在项目目录运行构建后的 exe 时，`sys.executable` 解析到项目目录下的 exe，`APP_ROOT` 就是项目目录，`DATA_DIR` 就是 `data/`。所以 `data/images/abc.png` 和 `![](images/abc.png)` 路径都能正确找到，exe 运行没问题。

---

## Implementation Steps

### Step 1: Create `ImageDir` config constant and ensure directory creation

**Modify** `app/config.py`:

```python
IMAGE_DIR = DATA_DIR / "images"
```

在 `JsonTagCatalogRepository` 和 `JsonTaskRepository` 的 `save` 方法中已有 `mkdir(parents=True, exist_ok=True)` 模式。图片保存时同样确保 `IMAGE_DIR` 存在。

### Step 2: Custom `MarkdownTextEdit` widget

**Create** `app/ui/components/markdown_text_edit.py`:

继承 `QTextEdit`，核心改动：

1. **加载描述**：用 `setMarkdown(task.description)` 替代 `setPlainText`，在 QTextDocument 中渲染 markdown
2. **保存描述**：缓存原始 markdown 源码。当用户所见即所得编辑（修改了渲染后的内容），用 `toMarkdown()` 提取。当用户切换到源码模式编辑，直接取缓存源码
3. **图片粘贴**：override `canInsertFromMimeData` + `insertFromMimeData`，检测 `source.hasImage()`，保存到 `IMAGE_DIR`，生成 `![](images/xxx.png)` 插入文档
4. **图片按钮**：不单独加按钮（用户选择了"按钮辅助插入 + 粘贴截图"），在 TaskDialog 中加一个"插入图片"toolbar按钮，调用 `QFileDialog` 选择文件，复制到 `IMAGE_DIR` 并插入 markdown 图片语法
5. **baseUrl 设置**：`document().setBaseUrl(QUrl.fromLocalFile(str(DATA_DIR) + "/"))`，让 `![](images/abc.png)` 相对路径能正确解析
6. **resourceProvider**：Qt 6.4+ 的 `document().setResourceProvider()` 回调，处理本地图片加载

**关键设计：源码/渲染切换**

QTextEdit 没有独立的"markdown模式标记"，但可以维护 `_raw_markdown` 缓存：
- 默认模式：所见即所得（`setMarkdown` 渲染后用户编辑）
- 源码模式：`setPlainText(_raw_markdown)`，用户直接编辑 markdown 源码
- 两者通过一个小按钮切换（类似 GitHub 的 Edit/Preview 切换）

但用户说"大部分情况下都是纯文本"，所以 **默认应该是渲染模式**。纯文本描述（无 markdown 语法）在 `setMarkdown` 下显示效果和 `setPlainText` 基本一致，对纯文本用户零影响。

**图片粘贴流程**：

```
用户 Ctrl+V 粘贴截图
→ MarkdownTextEdit.insertFromMimeData 检测 source.hasImage()
→ 生成文件名: paste_{timestamp}.png
→ QImage.save(IMAGE_DIR / filename, "PNG")
→ 在光标位置插入 ![](images/paste_xxx.png) markdown 图片语法
→ setMarkdown 重新渲染，图片显示
```

**图片按钮流程**：

```
用户点击"插入图片"按钮
→ QFileDialog 选择本地文件
→ 复制文件到 IMAGE_DIR (保持原文件名或生成唯一名避免冲突)
→ 在光标位置插入 ![](images/xxx.png)
→ setMarkdown 重新渲染
```

### Step 3: Modify `TaskDialog` description section

**Modify** `app/ui/components/task_dialog.py`:

1. 替换 `self.desc_edit = QTextEdit()` → `self.desc_edit = MarkdownTextEdit()`
2. 在 desc_edit 上方添加一个小的 toolbar：一个"插入图片"图标按钮 + 一个"源码/渲染切换"图标按钮
3. 保存描述时从 `MarkdownTextEdit` 获取原始 markdown 源码
4. 加载描述时用 `setMarkdown(task.description)`
5. 编辑框高度不变（120px fixed height）
6. toolbar 不占用 desc_edit 的空间，用独立的 QHBoxLayout 放在 desc_edit 上面

### Step 4: Modify `TaskInfoPopup` for markdown rendering

**Modify** `app/ui/components/task_card.py`:

当前 popup 用 `QLabel(task.description)` 渲染描述。改为：

1. 用 `QTextDocument` 的 `setMarkdown` 渲染描述内容
2. 通过 `QTextDocument.size()` 计算渲染后的高度，限制最多 10 行（约 10 行 × 18px = 180px）
3. 用一个自定义的 `QLabel` 设置 `setTextFormat(Qt.TextFormat.MarkdownText)` — QLabel 从 Qt 6.14 开始支持 `setTextFormat(MarkdownText)`，但更稳妥的做法是用 QTextDocument 渲染后转 HTML 给 QLabel，或直接用一个 mini QTextEdit（只读）
4. 宽度保持 300px

实际上 QLabel 有一个更简单的方案：Qt 6 的 QLabel 支持 `setTextFormat(Qt.TextFormat.MarkdownText)`。但我们需要行数限制，所以应该用 QTextDocument 渲染后截断。

**推荐方案**：在 popup 中用一个只读的 mini `QTextEdit` 替代 `QLabel`：
- 设置 `setMarkdown(task.description)`
- 设置 `setReadOnly(True)`
- 计算渲染后高度，超过 10 行时截断并添加 "..." 提示
- 设置 baseUrl 使图片能正确显示
- 禁止交互（NoFocus, 不响应点击）

### Step 5: Application layer — description length validation unchanged

`DESCRIPTION_MAX_LENGTH = 2_000` 仍然限制 markdown 源码的字符长度（不是渲染后长度）。对纯文本描述无影响，对 markdown 描述，2_000 字符足够承载大多数场景。如果未来需要调整可以改，当前不需要动。

### Step 6: Infrastructure — image directory persistence

图片文件存储在 `data/images/` 目录下，这个目录和 `data/tasks.json` / `data/tags.json` 同级。不需要新的 repository protocol — 图片文件不是业务数据，而是附件资源，直接用文件系统操作即可（`QImage.save()` / `shutil.copy2()`）。

`.gitignore` 中 `data/` 目录已经被忽略（之前 commit 已处理），所以 `data/images/` 也不会被 git 跟踪。

---

## Key Files to Modify/Create

| File | Change |
|------|--------|
| **Create** `app/ui/components/markdown_text_edit.py` | 新组件：继承 QTextEdit，支持 markdown 渲染、图片粘贴/插入、源码切换 |
| **Modify** `app/ui/components/task_dialog.py` | 替换 desc_edit 为 MarkdownTextEdit，添加图片插入按钮 |
| **Modify** `app/ui/components/task_card.py` | TaskInfoPopup 中渲染 markdown + 10行限制 + baseUrl |
| **Modify** `app/config.py` | 添加 `IMAGE_DIR = DATA_DIR / "images"` |

## Files NOT Modified (architecture alignment)

| Layer | File | Reason |
|-------|------|--------|
| Domain | `task.py` | `description: str = ""` 不变 — 存 markdown 源码 |
| Application | `commands.py`, `task_app.py` | description 字段不变，validation 不变 |
| Infrastructure | `json_task_repository.py` | 持久化仍然是纯字符串，markdown 是存储内容格式不是存储结构 |
| Services | `task_service.py` | 不变 — thin adapter 不感知描述格式 |

**关键原则**：markdown 是描述字段的 *内容格式*，不是架构变化。description 在 model/command/persistence 层仍然是一个 `str`，只是内容从纯文本变成了 markdown 源码。只有 UI 层需要感知格式并渲染。

---

## Verification

1. 纯文本描述（无 markdown）在编辑框和弹窗中显示效果和之前基本一致
2. 包含 markdown 的描述（标题、列表、粗体、链接）正确渲染
3. `![](images/xxx.png)` 图片在编辑框和弹窗中正确显示
4. 粘贴截图 → 自动保存到 data/images/ → 编辑框中显示图片 → 保存后重新加载图片仍可见
5. "插入图片"按钮 → 选择文件 → 图片复制到 data/images/ → 插入语法 → 渲染显示
6. 源码/渲染切换按钮正常工作
7. 构建后的 exe 在项目目录运行时，baseUrl 正确，图片能加载
8. description 超过 2000 字符时仍被 application 层拦截
9. `ruff check .` + `ruff format --check .` + `pytest` 全部通过
