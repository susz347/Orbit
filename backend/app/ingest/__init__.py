"""文件解析模块：支持 PDF、Markdown、TXT

实现拆分为：parsers（各类型解析器）、core（类型识别与分发），此处仅做导出。
"""
from .parsers import parse_pdf, parse_markdown, parse_text, PARSERS
from .core import SUPPORTED_TYPES, get_file_type, parse_file

__all__ = [
    "parse_pdf",
    "parse_markdown",
    "parse_text",
    "PARSERS",
    "SUPPORTED_TYPES",
    "get_file_type",
    "parse_file",
]
