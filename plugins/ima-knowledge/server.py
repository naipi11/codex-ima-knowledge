# /// script
# requires-python = ">=3.11,<3.15"
# dependencies = ["mcp==1.30.0", "httpx>=0.28,<0.29", "pywin32==312", "pypdf==7.1.1", "defusedxml==0.7.1"]
# ///
"""为 Codex 提供 ima 知识库只读工具。"""

import io
import sys
import zipfile
from typing import Annotated

from defusedxml import ElementTree
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field, StringConstraints
from pypdf import PdfReader

from ima_client import ImaError, NOTE, WIKI, download_media, request_data


server = FastMCP("ima-knowledge", log_level="WARNING")
readonly = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ListLimit = Annotated[int, Field(ge=1, le=20)]
BrowseLimit = Annotated[int, Field(ge=1, le=50)]
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@server.tool(title="列出或查找知识库", annotations=readonly)
def ima_list_bases(query: str = "", cursor: str = "", limit: ListLimit = 20) -> dict:
    """列出当前账号可见的知识库。query 可按库名筛选。返回条目的 kb_id 用作后续的 knowledge_base_id，kb_name 是库名。下一页使用 next_cursor。"""
    return request_data(WIKI + "search_knowledge_base", {"query": query, "cursor": cursor, "limit": limit})


@server.tool(title="查看知识库简介", annotations=readonly)
def ima_get_base(knowledge_base_id: Identifier) -> dict:
    """根据知识库 ID 获取名称、介绍和推荐问题。"""
    return request_data(WIKI + "get_knowledge_base", {"ids": [knowledge_base_id]})


@server.tool(title="浏览知识库文件夹", annotations=readonly)
def ima_browse(knowledge_base_id: Identifier, folder_id: Identifier | None = None,
               cursor: str = "", limit: BrowseLimit = 20) -> dict:
    """浏览知识库根目录或指定文件夹。返回条目、当前路径和腾讯的分页游标。"""
    body = {"knowledge_base_id": knowledge_base_id, "cursor": cursor, "limit": limit}
    if folder_id:
        body["folder_id"] = folder_id
    return request_data(WIKI + "get_knowledge_list", body)


@server.tool(title="搜索库内资料", annotations=readonly)
def ima_search(knowledge_base_id: Identifier, query: Identifier, cursor: str = "") -> dict:
    """在一个知识库里搜索关键词，返回资料标题、媒体 ID 及接口提供的命中片段。"""
    return request_data(WIKI + "search_knowledge", {
        "knowledge_base_id": knowledge_base_id, "query": query, "cursor": cursor,
    })


def extract_docx(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as doc:
        part = doc.getinfo("word/document.xml")
        if part.file_size > 32 * 1024 * 1024:
            raise ImaError("Word 文档正文过大，请在 ima 客户端打开。")
        xml = ElementTree.fromstring(doc.read(part))
    return "\n".join("".join(t.text or "" for t in p.iter(WORD + "t")) for p in xml.iter(WORD + "p"))


def extract_file(raw, media_type, page):
    try:
        if media_type == 1:
            pdf = PdfReader(io.BytesIO(raw))
            if pdf.is_encrypted and not pdf.decrypt(""):
                raise ImaError("此 PDF 需要密码，请在 ima 客户端打开。")
            count = len(pdf.pages)
            if page > count:
                raise ImaError(f"此 PDF 共 {count} 页，请调整页码。")
            return pdf.pages[page - 1].extract_text(), count
        if media_type == 3:
            return extract_docx(raw), 1
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16"), 1
        try:
            return raw.decode("utf-8-sig"), 1
        except UnicodeDecodeError:
            return raw.decode("gb18030"), 1
    except ImaError:
        raise
    except Exception:
        raise ImaError("原文格式或编码无法解析。Word 仅支持 DOCX，请在 ima 客户端打开此文件。") from None


@server.tool(title="读取资料正文", annotations=readonly)
def ima_read(media_id: Identifier, page: Annotated[int, Field(ge=1)] = 1,
             offset: Annotated[int, Field(ge=0)] = 0,
             max_chars: Annotated[int, Field(ge=1, le=16000)] = 6000) -> dict:
    """按媒体 ID 读取有权限的本人笔记、文本型 PDF、DOCX、TXT 或 Markdown。PDF 从第 1 页开始；长文本按字符偏移继续。"""
    data = request_data(WIKI + "get_media_info", {"media_id": media_id})
    kind = data.get("media_type")
    if page != 1 and kind != 1:
        raise ImaError("只有 PDF 按页读取；其他资料请使用 offset 继续。")
    if kind == 11 and (note_id := (data.get("notebook_ext_info") or {}).get("notebook_id")):
        note = request_data(NOTE + "get_doc_content", {"note_id": note_id, "target_content_format": 0})
        if not isinstance(note.get("content"), str):
            raise ImaError("腾讯未返回这篇笔记的正文。")
        content, pages = note["content"], 1
    else:
        info = data.get("url_info") or {}
        if kind not in (1, 3, 7, 13) or not info.get("url"):
            raise ImaError("此资料的格式或权限不支持在插件中读取正文。可使用库内搜索查看命中片段，或在 ima 客户端打开。")
        content, pages = extract_file(download_media(info), kind, page)
    if offset > len(content):
        raise ImaError(f"偏移量超过当前文本长度（{len(content)} 个字符）。")
    end = min(offset + max_chars, len(content))
    result = {"media_id": media_id, "page": page, "pages": pages, "offset": offset,
              "text": content[offset:end], "next_offset": end if end < len(content) else None,
              "next_page": page + 1 if end == len(content) and page < pages else None}
    if not content.strip():
        result["提示"] = "本页未提取到文本，可能是扫描件或空白页。" if kind == 1 else "此资料没有可提取的正文。"
    return result


if __name__ == "__main__":
    if sys.argv[1:] == ["--connect"]:
        from setup_window import run
        run()
    else:
        server.run(transport="stdio")
