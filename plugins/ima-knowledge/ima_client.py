"""腾讯 ima 只读接口和当前 Windows 用户的凭据存储。"""

import os
from urllib.parse import urlsplit

import httpx
import pywintypes
import win32cred


CREDENTIAL_TARGET = "Codex/ima-knowledge"
WIKI = "https://ima.qq.com/openapi/wiki/v1/"
NOTE = "https://ima.qq.com/openapi/note/v1/"
MAX_FILE_BYTES = 16 * 1024 * 1024


class ImaError(Exception):
    """可以直接展示给用户的错误。"""


def credentials():
    try:
        item = win32cred.CredRead(CREDENTIAL_TARGET, win32cred.CRED_TYPE_GENERIC)
    except pywintypes.error as exc:
        if exc.winerror != 1168:
            raise ImaError("无法读取 Windows 凭据管理器，请检查当前 Windows 登录账号。") from None
    else:
        return item["UserName"], item["CredentialBlob"].decode("utf-16-le")
    pair = (os.getenv("IMA_OPENAPI_CLIENTID"), os.getenv("IMA_OPENAPI_APIKEY"))
    if all(pair):
        return pair
    raise ImaError("尚未连接 ima。请在本机运行“连接我的知识库.cmd”，填写并验证腾讯凭据。")


def save_credentials(client_id, api_key):
    try:
        win32cred.CredWrite({
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": CREDENTIAL_TARGET,
            "UserName": client_id,
            "CredentialBlob": api_key,
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }, 0)
    except pywintypes.error:
        raise ImaError("腾讯已验证账号，但 Windows 凭据管理器保存失败。请检查系统凭据服务。") from None


def request_data(url, body, pair=None):
    client_id, api_key = pair or credentials()
    if any(not v.isascii() or not v.isprintable() for v in (client_id, api_key)):
        raise ImaError("凭据中含有非法字符，请重新复制 Client ID 和 API Key。")
    try:
        response = httpx.post(url, json=body, headers={
            "ima-openapi-clientid": client_id,
            "ima-openapi-apikey": api_key,
        }, timeout=20, follow_redirects=False)
    except httpx.RequestError:
        raise ImaError("连接腾讯 ima 失败，请检查网络或代理后重试。") from None
    if response.status_code in (401, 403):
        raise ImaError(f"腾讯拒绝访问（HTTP {response.status_code}）。请检查凭据和知识库访问权限。")
    if response.status_code == 429:
        raise ImaError("腾讯暂时限制请求频率，请稍后重试。")
    if not response.is_success:
        raise ImaError(f"腾讯接口返回 HTTP {response.status_code}，请稍后重试。")
    try:
        result = response.json()
    except ValueError:
        raise ImaError("腾讯接口未返回有效 JSON，请检查网络或代理。") from None
    if not isinstance(result, dict) or "code" not in result:
        raise ImaError("腾讯接口的响应格式无法识别。")
    if result["code"] != 0:
        msg = str(result.get("msg") or "请求未成功")
        for secret in (client_id, api_key):
            msg = msg.replace(secret, "〔已隐藏〕")
        raise ImaError(f"腾讯返回错误 {result['code']}，{msg[:240]}")
    data = result.get("data")
    if not isinstance(data, dict):
        raise ImaError("腾讯接口缺少数据字段。")
    return data


def download_media(info):
    """仅使用该文件的临时请求头，限制原文来源和大小。"""
    url = info.get("url", "")
    parts = urlsplit(url)
    host = parts.hostname or ""
    trusted = host == "ima.qq.com" or host.endswith((".ima.qq.com", ".myqcloud.com"))
    if not trusted or parts.scheme != "https" or parts.port not in (None, 443) or parts.username or parts.password:
        raise ImaError("此资料的原文位于外部站点，请在 ima 客户端打开。")
    headers = {k: v for k, v in (info.get("headers") or {}).items()
               if k.lower() not in {"host", "cookie", "proxy-authorization", "ima-openapi-clientid", "ima-openapi-apikey"}}
    try:
        with httpx.stream("GET", url, headers=headers, timeout=20, follow_redirects=False) as response:
            if not response.is_success:
                raise ImaError("腾讯原文链接已过期、发生跳转或无权访问，请在 ima 客户端查看。")
            content = bytearray()
            for chunk in response.iter_bytes(chunk_size=65536):
                if len(content) + len(chunk) > MAX_FILE_BYTES:
                    raise ImaError("原文超过插件单次读取上限 16 MiB，请使用库内搜索或在 ima 打开。")
                content.extend(chunk)
            return bytes(content)
    except httpx.RequestError:
        raise ImaError("原文下载失败，请稍后重试或在 ima 客户端打开。") from None
