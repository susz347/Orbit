"""各文件类型的解析器实现"""


def parse_pdf(filepath: str) -> str:
    """解析 PDF 文件，提取纯文本"""
    from PyPDF2 import PdfReader
    reader = PdfReader(filepath)
    texts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            texts.append(text)
    return "\n\n".join(texts)


def parse_markdown(filepath: str) -> str:
    """读取 Markdown 文件，保留原始格式"""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def parse_text(filepath: str) -> str:
    """读取纯文本文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


PARSERS = {
    "pdf": parse_pdf,
    "markdown": parse_markdown,
    "text": parse_text,
}
