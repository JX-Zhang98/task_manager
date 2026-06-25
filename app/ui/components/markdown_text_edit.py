from __future__ import annotations

import base64
import re
import shutil
import time
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QImage, QTextCursor, QTextDocument, QTextImageFormat
from PyQt6.QtWidgets import QTextEdit

from app.config import IMAGE_DIR

# Regex to match data:image/<format>;base64,<data> inside HTML <img> src attributes.
_DATA_URI_RE = re.compile(
    r'src=["\']data:image/(\w+);base64,([A-Za-z0-9+/=\s]+)["\']',
    re.IGNORECASE,
)


class MarkdownTextEdit(QTextEdit):
    """QTextEdit subclass that renders Markdown (WYSIWYG by default)
    and supports image pasting / file insertion.

    Mode toggle:
      - Rendered (default): setMarkdown() renders the description
      - Source: setPlainText() shows raw Markdown for editing

    The raw Markdown source is always cached in ``_raw_markdown``.
    ``toPlainText()`` in rendered mode returns the rendered text,
    not the source.  Use ``markdown_source()`` to get the Markdown
    regardless of current mode.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._raw_markdown = ""
        self._source_mode = False  # False = rendered/WYSIWYG, True = source

        # Enable baseUrl so relative image paths like ![](images/abc.png)
        # resolve correctly.
        self.document().setBaseUrl(QUrl.fromLocalFile(str(IMAGE_DIR.parent) + "/"))

    # ── Qt resource loading ──────────────────────────────────────────

    def loadResource(self, type: int, url: QUrl):
        """Override loadResource to resolve relative image URLs against baseUrl.

        Qt bug (QTBUG-65346, QTBUG-89753): setBaseUrl does not reliably
        resolve relative paths parsed by setMarkdown().  This override
        manually resolves relative URLs and loads local images.
        Results are automatically cached by QTextDocument.
        """
        if type == QTextDocument.ResourceType.ImageResource.value:
            resolved = self.document().baseUrl().resolved(url) if url.isRelative() else url
            image = QImage(resolved.toLocalFile())
            if not image.isNull():
                return image
        return super().loadResource(type, url)

    # ── Public API ────────────────────────────────────────────────────

    def set_description(self, markdown_text: str) -> None:
        """Load a Markdown description into the editor."""
        self._raw_markdown = markdown_text or ""
        self._apply_content()

    def markdown_source(self) -> str:
        """Return the current Markdown source (regardless of mode).

        In rendered mode the user may have edited the rich text directly.
        We convert back via ``toMarkdown()`` which may differ from the
        original source, but preserves meaning.
        """
        if self._source_mode:
            return self.toPlainText()
        # User edited in WYSIWYG — convert back to Markdown.
        return self.document().toMarkdown(QTextDocument.MarkdownFeature.MarkdownDialectGitHub)

    def is_source_mode(self) -> bool:
        return self._source_mode

    def toggle_source_mode(self) -> None:
        """Switch between rendered and source editing."""
        if self._source_mode:
            # Leaving source mode — cache what the user typed.
            self._raw_markdown = self.toPlainText()
            self._source_mode = False
            self._apply_content()
        else:
            # Leaving rendered mode — snapshot the markdown.
            self._raw_markdown = self.markdown_source()
            self._source_mode = True
            self.setPlainText(self._raw_markdown)

    def insert_image_file(self, filepath: str | Path) -> None:
        """Copy an image into IMAGE_DIR and insert it at the cursor position."""
        src = Path(filepath)
        if not src.is_file():
            return

        IMAGE_DIR.mkdir(parents=True, exist_ok=True)

        # Generate a unique name to avoid collisions.
        dest_name = f"{src.stem}_{int(time.time())}{src.suffix}"
        dest = IMAGE_DIR / dest_name
        shutil.copy2(src, dest)

        if self._source_mode:
            md_syntax = f"\n![](images/{dest_name})\n"
            cursor = self.textCursor()
            cursor.insertText(md_syntax)
        else:
            # Rendered mode: insert QTextImageFormat directly at cursor
            # so the image appears at the correct position.
            image = QImage(str(dest))
            if image.isNull():
                return

            # Register image as document resource for display.
            image_url = QUrl(f"images/{dest_name}")
            self.document().addResource(QTextDocument.ResourceType.ImageResource, image_url, image)

            # Insert image format at cursor position.
            cursor = self.textCursor()
            img_fmt = self._make_scaled_image_format(f"images/{dest_name}", image)
            cursor.insertImage(img_fmt)

            # Sync the markdown cache from current document state.
            self._raw_markdown = self.markdown_source()

    # ── Clipboard paste ──────────────────────────────────────────────

    def canInsertFromMimeData(self, source) -> bool:
        # Accept HTML (which may contain images) and pure images.
        if source.hasHtml() or source.hasImage():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source) -> None:
        # Priority 1: HTML with embedded images (mixed text+image content).
        # This preserves both text AND images from e.g. browser copy.
        if source.hasHtml():
            html = source.html()
            if "<img" in html.lower():
                if self._source_mode:
                    md_text = self._html_to_markdown(html)
                    cursor = self.textCursor()
                    cursor.insertText(md_text)
                else:
                    processed_html, resources = self._extract_data_uri_images(html)
                    # Register all extracted images as document resources.
                    for name, img in resources:
                        self.document().addResource(
                            QTextDocument.ResourceType.ImageResource, QUrl(name), img
                        )
                    cursor = self.textCursor()
                    cursor.insertHtml(processed_html)
                    self._raw_markdown = self.markdown_source()
                    # Scale any images that are too wide.
                    self._scale_images_to_width(max(int(self.width() * 0.9), 240))
                return

        # Priority 2: Pure image (screenshot / single image copy).
        if source.hasImage():
            image = source.imageData()
            if isinstance(image, QImage) and not image.isNull():
                IMAGE_DIR.mkdir(parents=True, exist_ok=True)

                filename = f"paste_{int(time.time())}.png"
                dest = IMAGE_DIR / filename
                image.save(str(dest), "PNG")

                if self._source_mode:
                    md_syntax = f"\n![](images/{filename})\n"
                    cursor = self.textCursor()
                    cursor.insertText(md_syntax)
                else:
                    image_url = QUrl(f"images/{filename}")
                    self.document().addResource(
                        QTextDocument.ResourceType.ImageResource, image_url, image
                    )
                    cursor = self.textCursor()
                    img_fmt = self._make_scaled_image_format(f"images/{filename}", image)
                    cursor.insertImage(img_fmt)
                    self._raw_markdown = self.markdown_source()
                return

        # Priority 3: Default — plain text, HTML without images, etc.
        super().insertFromMimeData(source)

    # ── Helpers ───────────────────────────────────────────────────────

    def _make_scaled_image_format(self, name: str, image: QImage) -> QTextImageFormat:
        """Create a QTextImageFormat scaled proportionally to fit editor width."""
        img_fmt = QTextImageFormat()
        img_fmt.setName(name)
        editor_width = max(int(self.width() * 0.9), 240)
        if image.width() > editor_width and editor_width > 0:
            scale = editor_width / image.width()
            img_fmt.setWidth(int(editor_width))
            img_fmt.setHeight(int(image.height() * scale))
        return img_fmt

    def _scale_images_to_width(self, target_width: int) -> None:
        """Scale all images in the document proportionally to fit within *target_width*.

        Iterates through the document's fragments, finds ``QTextImageFormat``
        instances whose natural width exceeds *target_width*, and replaces
        them with proportionally scaled versions.
        """
        if target_width <= 0:
            return

        doc = self.document()

        # Collect image info first (before modifying the document).
        images_to_scale: list[tuple[int, int, str, int, int]] = []
        block = doc.firstBlock()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().isImageFormat():
                    img_fmt = frag.charFormat().toImageFormat()
                    img_name = img_fmt.name()

                    # Get natural image dimensions from file.
                    url = QUrl(img_name)
                    resolved_url = doc.baseUrl().resolved(url) if url.isRelative() else url
                    actual_image = QImage(resolved_url.toLocalFile())
                    if not actual_image.isNull() and actual_image.width() > target_width:
                        scale = target_width / actual_image.width()
                        new_width = int(target_width)
                        new_height = int(actual_image.height() * scale)
                        images_to_scale.append(
                            (frag.position(), frag.length(), img_name, new_width, new_height)
                        )
                it += 1
            block = block.next()

        if not images_to_scale:
            return

        # Replace images in reverse order to preserve positions.
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        for pos, length, name, width, height in reversed(images_to_scale):
            cursor.setPosition(pos)
            cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            new_fmt = QTextImageFormat()
            new_fmt.setName(name)
            new_fmt.setWidth(width)
            new_fmt.setHeight(height)
            cursor.insertImage(new_fmt)
        cursor.endEditBlock()

    def _extract_data_uri_images(self, html: str) -> tuple[str, list[tuple[str, QImage]]]:
        """Extract data:image/...;base64,... URIs from HTML, save to
        IMAGE_DIR, rewrite HTML src to local relative paths.

        Returns (processed_html, [(resource_name, QImage), ...]).
        """
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        resources: list[tuple[str, QImage]] = []

        ext_map = {
            "jpeg": "jpg",
            "jpg": "jpg",
            "png": "png",
            "gif": "gif",
            "webp": "webp",
            "bmp": "bmp",
        }

        for i, match in enumerate(list(_DATA_URI_RE.finditer(html))):
            img_format = match.group(1).lower()
            b64_data = match.group(2).strip()

            image_data = base64.b64decode(b64_data)
            image = QImage()
            image.loadFromData(image_data)

            if image.isNull():
                continue

            suffix = ext_map.get(img_format, "png")
            dest_name = f"paste_{int(time.time())}_{i}.{suffix}"
            dest_path = IMAGE_DIR / dest_name

            # Save the image file.
            qt_format = "JPEG" if suffix == "jpg" else suffix.upper()
            image.save(str(dest_path), qt_format)

            # Rewrite HTML: replace data: URI with local relative path.
            html = html.replace(match.group(0), f'src="images/{dest_name}"')

            resources.append((f"images/{dest_name}", image))

        return html, resources

    @staticmethod
    def _html_to_markdown(html: str) -> str:
        """Convert HTML to Markdown using Qt's built-in conversion.

        Used in source mode to insert pasted HTML content as Markdown text.
        """
        temp_doc = QTextDocument()
        temp_doc.setHtml(html)
        return temp_doc.toMarkdown(QTextDocument.MarkdownFeature.MarkdownDialectGitHub)

    # ── Internal ──────────────────────────────────────────────────────

    def _preprocess_for_render(self, markdown: str) -> str:
        """Add Markdown hard-break markers so single newlines produce
        visible line breaks in rendered mode.

        Standard Markdown treats single newlines within a paragraph as
        soft breaks (rendered as spaces, not line breaks). For task
        descriptions, users expect each newline to produce a visible
        line break, similar to plain-text behavior.

        This function adds two trailing spaces (the Markdown hard-break
        syntax ``  \\n``) before each single newline that is not already
        part of a paragraph break (``\\n\\n``) or already a hard break
        (ending with two trailing spaces).
        """
        if not markdown:
            return markdown

        lines = markdown.split("\n")
        result = []
        for i, line in enumerate(lines):
            result.append(line)
            if i >= len(lines) - 1:
                continue  # Last line — no newline after it

            # If next line is empty, we already have a paragraph break.
            if lines[i + 1] == "":
                continue
            # If current line is empty (blank line in a paragraph break), skip.
            if line == "":
                continue
            # If current line already ends with two spaces (hard-break marker), skip.
            if line.endswith("  ") and line.rstrip(" ") != line.rstrip("  "):
                continue

            # Add hard-break marker (two trailing spaces) so the
            # single newline renders as a visible line break.
            result[-1] = line + "  "

        return "\n".join(result)

    def _apply_content(self) -> None:
        """Render the cached Markdown source according to current mode."""
        if self._source_mode:
            self.setPlainText(self._raw_markdown)
        else:
            preprocessed = self._preprocess_for_render(self._raw_markdown)
            self.setMarkdown(preprocessed)
            # Scale images that are wider than the editor.
            self._scale_images_to_width(max(int(self.width() * 0.9), 240))
