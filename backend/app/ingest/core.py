"""文件解析入口：类型识别与解析分发"""

import os
from typing import Optional

from .parsers import PARSERS


SUPPORTED_TYPES = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".txt": "text",
    ".markdown": "markdown",
}


def get_file_type(filename: str) -> Optional[str]:
    ext = os.path.splitext(filename)[1].lower()
    return SUPPORTED_TYPES.get(ext)


def parse_file(filepath: str) -> tuple[str, str]:
    """
    解析文件，返回 (文本内容, 文件类型)
    """
    file_type = get_file_type(filepath)
    if not file_type:
        raise ValueError(f"不支持的文件类型: {os.path.splitext(filepath)[1]}")

    parser = PARSERS[file_type]
    text = parser(filepath)
    return text, file_type
