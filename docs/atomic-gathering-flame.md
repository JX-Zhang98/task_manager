# Markdown 支持修复计划

## Context

根据 `floofy-wiggling-torvalds.md` 计划完成了初步开发，lint/format/test 全部通过（66 tests passed）。但检查发现了 3 个问题，用户特别要求**渲染模式下图片必须在光标位置插入**，且要支持**粘贴文字+图片混合内容**。

---

## 问题清单

### 问题 1：图片无法显示 — 缺少 `loadResource`（严重）

Qt 已知 Bug（QTBUG-65346、QTBUG-89753）：`setBaseUrl()` 对 `setMarkdown()` 解析的相对图片路径**不可靠**。`setMarkdown("![](images/abc.png)")` 将相对 URL 存入文档时不经过 baseUrl 解析，导致图片加载失败。

**受影响位置**：
- `markdown_text_edit.py:35` — 只设了 baseUrl，没有 loadResource
- `task_card.py:189` — popup 同样只有 baseUrl

**修复方案**：在 `MarkdownTextEdit` 中 override `loadResource`（结果被 Qt 自动缓存，优先于 `setResourceProvider`）。popup 改用 `MarkdownTextEdit` 而非裸 `QTextEdit`，复用同一 loadResource。

```python
def loadResource(self, type: int, url: QUrl):
    if type == QTextDocument.ResourceType.ImageResource.value:
        if url.isRelative():
            resolved = self.document().baseUrl().resolved(url)
        else:
            resolved = url
        image = QImage(resolved.toLocalFile())
        if not image.isNull():
            return image
    return super().loadResource(type, url)
```

### 问题 2：Popup 截断逻辑无效（中等）

当前代码在文档末尾追加 `"…"` 但没有删除任何内容，且 `setFixedHeight(180)` + 隐藏滚动条会将 `"…"` 也裁剪掉（它在可视区域下方），用户看不到截断提示。

**修复方案**：删除无效的 cursor.insertText + re-render 逻辑，改用独立 QLabel 指示截断：

```python
if doc_height <= 180:
    desc_view.setFixedHeight(int(doc_height) + 4)
else:
    desc_view.setFixedHeight(180)
    ellipsis = QLabel("…")
    ellipsis.setStyleSheet(...)
    v_layout.addWidget(ellipsis)
```

### 问题 3：渲染模式图片追加末尾而非光标位置（中等）

当前 `insert_image_file()` 和 `insertFromMimeData()` 在渲染模式下都执行 `self._raw_markdown += md_syntax`（追加到末尾），而非光标位置。且 `insertFromMimeData` 中 `source.hasImage()` 优先于 `source.hasHtml()`，导致粘贴文字+图片混合内容时**只处理图片、丢弃文字**。

**核心洞察**：Qt 没有将渲染文档光标位置映射回 markdown 源码位置的 API。但项目已在渲染模式下以 `document().toMarkdown()` 为 source-of-truth，所以最佳方案是**直接在渲染文档中插入 QTextImageFormat**，避开不可能的源码位置映射。

**修复方案**：

1. **图片插入/粘贴**：在渲染模式下用 `QTextImageFormat` 在光标位置直接插入，用 `document().addResource()` 注册图片资源，再通过 `toMarkdown()` 同步 `_raw_markdown`。

2. **混合内容粘贴**：改变 `insertFromMimeData` 优先级顺序 — `hasHtml()` 且含 `<img>` 标签时优先处理 HTML（保留文字+图片），再处理纯截图 `hasImage()`，最后 `super()` 处理纯文本。对于 HTML 中的 `data:image/...;base64,...` 内嵌图片，提取并保存到 IMAGE_DIR，改写 HTML src 为本地路径后 `insertHtml()`。

---

## 修改文件清单

| 文件 | 改动 |
|------|------|
| **`app/ui/components/markdown_text_edit.py`** | 主要修改：添加 `loadResource` override；`insert_image_file` 渲染模式改用 QTextImageFormat；`insertFromMimeData` 重写优先级+混合内容处理；添加 `_extract_data_uri_images` 和 `_html_to_markdown` 辅助方法；新 imports |
| **`app/ui/components/task_card.py`** | popup 改用 MarkdownTextEdit（复用 loadResource）；移除无效截断逻辑改为 QLabel "…"；移除不再需要的 QUrl/QTextCursor/QTextEdit imports |
| **`app/ui/components/task_dialog.py`** | 无改动（已正确集成 MarkdownTextEdit） |
| **`app/config.py`** | 无改动（IMAGE_DIR 已定义） |

---

## 详细实现步骤

### Step 1: `markdown_text_edit.py` — 添加 `loadResource`

在 `MarkdownTextEdit` 类中添加 `loadResource` override，使 `setMarkdown()` 解析的相对图片路径能正确显示。

需要 import `QTextDocument` 已存在，追加 `QImage` 已存在。确认 `QTextDocument.ResourceType.ImageResource` 可用。

### Step 2: `markdown_text_edit.py` — 重写 `insert_image_file` 渲染模式

```python
def insert_image_file(self, filepath: str | Path) -> None:
    src = Path(filepath)
    if not src.is_file():
        return
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    dest_name = f"{src.stem}_{int(time.time())}{src.suffix}"
    dest = IMAGE_DIR / dest_name
    shutil.copy2(src, dest)

    if self._source_mode:
        md_syntax = f"\n![](images/{dest_name})\n"
        cursor = self.textCursor()
        cursor.insertText(md_syntax)
    else:
        image = QImage(str(dest))
        if image.isNull():
            return
        # 注册图片为文档资源
        image_url = QUrl(f"images/{dest_name}")
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, image_url, image
        )
        # 在光标位置插入 QTextImageFormat
        cursor = self.textCursor()
        img_fmt = QTextImageFormat()
        img_fmt.setName(f"images/{dest_name}")
        cursor.insertImage(img_fmt)
        # 同步 _raw_markdown
        self._raw_markdown = self.markdown_source()
```

需新增 import：`QTextImageFormat` from `PyQt6.QtGui`

### Step 3: `markdown_text_edit.py` — 重写 `insertFromMimeData`

改变优先级：HTML 含 `<img>` → 纯截图 → super()。

渲染模式下：
- 纯截图：QImage save → addResource → QTextImageFormat 插入光标 → sync _raw_markdown
- HTML 含 `<img>`：提取 data: URI 图片保存本地 → 改写 HTML src → `insertHtml()` → addResource → sync _raw_markdown
- HTML 含外部 URL 图片：保留原 URL，`insertHtml()` 处理

源码模式下：
- 纯截图：`cursor.insertText(md_syntax)` （不变）
- HTML 含 `<img>`：转换为 markdown 后 `cursor.insertText(md_text)` （通过临时 QTextDocument 转换）

```python
def insertFromMimeData(self, source) -> None:
    # 优先处理 HTML 混合内容（文字+图片）
    if source.hasHtml():
        html = source.html()
        if "<img" in html.lower():
            if self._source_mode:
                md_text = self._html_to_markdown(html)
                cursor = self.textCursor()
                cursor.insertText(md_text)
            else:
                processed_html, resources = self._extract_data_uri_images(html)
                # 先注册所有图片资源
                for name, img in resources:
                    self.document().addResource(
                        QTextDocument.ResourceType.ImageResource,
                        QUrl(name), img
                    )
                cursor = self.textCursor()
                cursor.insertHtml(processed_html)
                self._raw_markdown = self.markdown_source()
            return

    # 纯截图粘贴
    if source.hasImage():
        image = source.imageData()
        if image is None:
            return super().insertFromMimeData(source)
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"paste_{int(time.time())}.png"
        dest = IMAGE_DIR / filename
        image.save(str(dest), "PNG")

        if self._source_mode:
            cursor = self.textCursor()
            cursor.insertText(f"\n![](images/{filename})\n")
        else:
            image_url = QUrl(f"images/{filename}")
            self.document().addResource(
                QTextDocument.ResourceType.ImageResource, image_url, image
            )
            cursor = self.textCursor()
            img_fmt = QTextImageFormat()
            img_fmt.setName(f"images/{filename}")
            cursor.insertImage(img_fmt)
            self._raw_markdown = self.markdown_source()
        return

    super().insertFromMimeData(source)
```

### Step 4: `markdown_text_edit.py` — 添加辅助方法

**`_extract_data_uri_images(html)`**：从 HTML 中提取 `data:image/...;base64,...` 图片，保存到 IMAGE_DIR，改写 HTML src 为本地路径，返回 (processed_html, resources_list)。

**`_html_to_markdown(html)`**：在源码模式下将 HTML 转为 markdown，用临时 QTextDocument 做 setHtml → toMarkdown 转换。

需新增 imports：`re`, `base64` from stdlib；`QTextImageFormat` from `PyQt6.QtGui`；`QBuffer` from `PyQt6.QtCore`（如果需要）

### Step 5: `task_card.py` — popup 改用 MarkdownTextEdit + 修复截断

**改动**：
1. Import `MarkdownTextEdit` 替代 `QTextEdit`
2. popup 中 `desc_view = MarkdownTextEdit()` 替代 `desc_view = QTextEdit()` — 复用 loadResource，baseUrl 已在 __init__ 中设置
3. 用 `desc_view.set_description(task.description)` 替代手动 `setMarkdown` + baseUrl 设置
4. 截断：移除 cursor.insertText + re-render 逻辑，改为独立 QLabel "…"

**移除的 imports**：`QUrl`（baseUrl 由 MarkdownTextEdit 内部处理）、`QTextCursor`（不再需要）、`QTextEdit`（改用 MarkdownTextEdit）

**新增的 import**：`from app.ui.components.markdown_text_edit import MarkdownTextEdit`

### Step 6: 可选清理 — `canInsertFromMimeData`

当前的 `canInsertFromMimeData` 在 `source.hasImage()` 时返回 True。由于 `insertFromMimeData` 现在先检查 `source.hasHtml()`，这里无需改动 — Qt 会在调用 `insertFromMimeData` 前先调用 `canInsertFromMimeData` 来判断是否可以粘贴。HTML 和 Image 都能粘贴，所以 `canInsertFromMimeData` 应该对两者都返回 True，当前逻辑已经正确。

---

## 验证步骤

1. `ruff check .` + `ruff format --check .` + `pytest` 全部通过
2. 纯文本描述在编辑框和弹窗中显示效果与之前一致
3. Markdown 格式描述（标题、列表、粗体）正确渲染
4. `![](images/xxx.png)` 图片在编辑框和弹窗中**正确显示**（验证 loadResource 修复）
5. 渲染模式下在光标中间位置插入图片 → 图片出现在光标处，不在末尾
6. 源码模式下插入图片 → 在光标位置插入 markdown 文本
7. 粘贴截图 → 图片在光标位置显示
8. 粘贴浏览器中文字+图片混合内容 → **文字和图片都保留**，图片保存到本地
9. Popup 中超过 10 行的描述 → 固定高度 180px + 下方显示 "…" 标签
10. 源码/渲染切换后图片仍正确显示
11. description 超过 2000 字符时 application 层仍拦截

**关键验证项**：`toMarkdown()` 对 QTextImageFormat 输出的图片语法格式。需实测确认输出为 `![](images/abc.png)` 或类似可接受格式。如果输出不理想（如带多余 alt text），需追加后处理。
