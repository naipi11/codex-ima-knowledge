"""验证只读请求映射、原文分页和凭据处理，使用合成数据。"""

import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "ima-knowledge"))
import httpx
from pypdf import PdfWriter

import ima_client
import server


class ImaTests(unittest.TestCase):
    def test_windows_credential_roundtrip(self):
        target = "Codex/ima-test-" + uuid4().hex
        with patch.object(ima_client, "CREDENTIAL_TARGET", target):
            ima_client.save_credentials("test-id", "test-key")
            try:
                self.assertEqual(ima_client.credentials(), ("test-id", "test-key"))
            finally:
                ima_client.win32cred.CredDelete(target, ima_client.win32cred.CRED_TYPE_GENERIC)

    @patch("server.request_data")
    def test_catalog_and_folder_cursors(self, api):
        api.return_value = {"is_end": False, "next_cursor": "下一页"}
        self.assertEqual(server.ima_list_bases()["next_cursor"], "下一页")
        api.assert_called_with(ima_client.WIKI + "search_knowledge_base", {"query": "", "cursor": "", "limit": 20})
        server.ima_browse("库", "目录", "下一页", 7)
        api.assert_called_with(ima_client.WIKI + "get_knowledge_list", {
            "knowledge_base_id": "库", "folder_id": "目录", "cursor": "下一页", "limit": 7,
        })
        server.ima_browse("库")
        self.assertNotIn("folder_id", api.call_args.args[1])
        server.ima_search("库", "桥梁", "接续")
        api.assert_called_with(ima_client.WIKI + "search_knowledge", {
            "knowledge_base_id": "库", "query": "桥梁", "cursor": "接续",
        })
        server.ima_get_base("库")
        api.assert_called_with(ima_client.WIKI + "get_knowledge_base", {"ids": ["库"]})

    @patch("server.request_data")
    def test_note(self, api):
        api.side_effect = [{"media_type": 11, "notebook_ext_info": {"notebook_id": "笔记"}}, {"content": "甲乙丙"}]
        r = server.ima_read("资料", offset=1, max_chars=1)
        self.assertEqual((r["text"], r["next_offset"]), ("乙", 2))
        api.assert_called_with(ima_client.NOTE + "get_doc_content", {"note_id": "笔记", "target_content_format": 0})

    @patch("server.request_data", return_value={"media_type": 1})
    def test_unavailable_original(self, api):
        with self.assertRaisesRegex(ima_client.ImaError, "权限"):
            server.ima_read("资料")

    def test_docx_and_encoded_text(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as doc:
            doc.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>桥梁</w:t></w:r></w:p></w:document>')
        self.assertEqual(server.extract_file(data.getvalue(), 3, 1), ("桥梁", 1))
        for encoding in ("utf-8-sig", "utf-16", "gb18030"):
            self.assertEqual(server.extract_file("桥梁".encode(encoding), 13, 1)[0], "桥梁")

    @patch("server.request_data", return_value={"media_type": 1, "url_info": {"url": "示例"}})
    @patch("server.download_media")
    def test_pdf_pages(self, download, api):
        buf = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_blank_page(width=100, height=100)
        writer.write(buf)
        download.return_value = buf.getvalue()
        first = server.ima_read("文档")
        self.assertEqual((first["pages"], first["next_page"]), (2, 2))
        self.assertIn("未提取到文本", first["提示"])
        self.assertIsNone(server.ima_read("文档", page=2)["next_page"])
        with self.assertRaisesRegex(ima_client.ImaError, "共 2 页"):
            server.ima_read("文档", page=3)

    @patch("ima_client.httpx.stream")
    def test_external_media_is_not_fetched(self, stream):
        with self.assertRaisesRegex(ima_client.ImaError, "外部站点"):
            ima_client.download_media({"url": "https://example.org/file", "headers": {"Authorization": "临时凭据"}})
        stream.assert_not_called()

    @patch("ima_client.httpx.post")
    def test_api_errors(self, post):
        post.return_value = httpx.Response(200, json={"code": 110030, "msg": "denied sample-secret"})
        with self.assertRaises(ima_client.ImaError) as cm:
            ima_client.request_data(ima_client.WIKI + "get_knowledge_list", {}, ("sample-id", "sample-secret"))
        self.assertIn("110030", str(cm.exception))
        self.assertNotIn("sample-secret", str(cm.exception))
        self.assertFalse(post.call_args.kwargs["follow_redirects"])
        post.return_value = httpx.Response(401)
        with self.assertRaisesRegex(ima_client.ImaError, "401"):
            ima_client.request_data(ima_client.WIKI + "get_knowledge_list", {}, ("sample-id", "sample-secret"))


if __name__ == "__main__":
    unittest.main()
