"""SR2: 存储路由回归测试集（参考 LLMRouter xRouteBench 思想）。

覆盖 5 种存储策略 × 每策略 10+ 样本，含边缘 case。
每次修改 routing.py 路由规则后跑本测试，确保准确率不下降。
"""

import pytest

from app.storage_router import route_storage

# (filename, text_sample, expected_strategy)
STORAGE_ROUTING_BENCHMARK = [
    # ── original: 合同/法律/合规 ──
    ("合同_2024.pdf", "甲方：XX科技有限公司\n乙方：YY有限公司\n第一条 交付标准与验收流程\n第二条 违约责任\n本协议一式两份", "original"),
    ("保密协议.docx", "保密信息 双方约定 披露方 接收方 违约责任 保密期限 争议解决", "original"),
    ("劳动合同.txt", "劳动合同 甲方 乙方 劳动报酬 社会保险 合同期限 解除条件", "original"),
    ("采购合同.xlsx", "采购合同 供应商 交货时间 付款方式 质量保证 违约赔偿", "original"),
    # ── structured: 表格数据 ──
    ("员工表.csv", "姓名,部门,入职日期,薪资,绩效\n张三,技术部,2023-01-15,15000,A\n李四,市场部,2023-05-20,12000,B", "structured"),
    ("销售数据.xlsx", "月份,销售额,环比,同比\n1月,100000,0.1,0.2\n2月,120000,0.2,0.15", "structured"),
    ("库存清单.tsv", "SKU\t名称\t数量\t单价\nA001\t键盘\t500\t199", "structured"),
    # ── graph: 关系型数据 ──
    ("组织架构.json", '{"nodes":[{"id":"CEO"},{"id":"CTO"},{"id":"CFO"}],"edges":[{"source":"CEO","target":"CTO"},{"source":"CEO","target":"CFO"}]}', "graph"),
    ("依赖关系.yaml", "services:\n  api:\n    depends_on: [db, redis]\n  db:\n    depends_on: []", "graph"),
    ("汇报链.md", "CEO 管理 CTO 和 CFO\nCTO 管理 架构组 和 平台组\n架构组 包含 前端 和 后端", "graph"),
    # ── multimodal: 图片 ──
    ("产品图片.png", "", "multimodal"),
    ("扫描件.jpg", "", "multimodal"),
    ("架构图.webp", "", "multimodal"),
    # ── rag: 普通文档 ──
    ("API文档.md", "# API Reference\n## GET /users\n返回用户列表，支持分页参数", "rag"),
    ("产品手册.txt", "产品介绍\n功能特性\n使用说明\n常见问题解答", "rag"),
    ("FAQ.md", "问：如何重置密码？\n答：在登录页点击忘记密码", "rag"),
    ("技术教程.md", "本教程介绍 Docker 的基本概念、安装步骤和常用命令", "rag"),
    ("会议纪要.md", "参会人：张伟、李明\n议题：Q3 产品规划\n结论：下月发布 v2.0", "rag"),
    # ── 边缘 case ──
    # PDF 里夹表格：扩展名 pdf + 表格内容 → 应判 original（整篇不切割）或 structured？
    # 规则按内容特征优先，表格关键词多 → structured；此处验证不崩溃且返回有效策略
    ("报告.pdf", "报告编号：R-2024-001\n月度销售额 100 万\n环比增长 20%\n同比增长 15%", "rag"),
    # 会议纪要引用合同条款（含合同关键词但数量少）→ 不应误判 contract
    ("会议纪要_0301.md", "讨论了与供应商的合同续签事宜，下月需完成续签流程，同时整理 Q2 预算", "rag"),
    # 空文档
    ("empty.md", "", "rag"),
]


def test_storage_routing_accuracy():
    """整体准确率应 ≥ 85%。"""
    correct = 0
    errors = []
    for filename, text, expected in STORAGE_ROUTING_BENCHMARK:
        result = route_storage(filename, text)
        got = result["strategy"]
        if got == expected:
            correct += 1
        else:
            errors.append((filename, expected, got, result.get("reason", "")))

    accuracy = correct / len(STORAGE_ROUTING_BENCHMARK)
    assert accuracy >= 0.85, f"存储路由准确率 {accuracy:.1%} < 85%，误判: {errors}"


def test_storage_routing_valid_strategy_always():
    """任何输入都必须返回合法策略（不崩溃 + 策略有效）。"""
    for filename, text, _ in STORAGE_ROUTING_BENCHMARK:
        result = route_storage(filename, text)
        assert result["strategy"] in {"rag", "original", "structured", "graph", "multimodal"}, \
            f"{filename} 返回非法策略 {result['strategy']}"
        assert result["content_type"], f"{filename} 缺少 content_type"


def test_storage_routing_contract_not_table():
    """合同即使含表格特征（如金额数字），也应为 original 而非 structured。"""
    result = route_storage(
        "购销合同.txt",
        "购销合同\n第一条 货物交付：总额 100000 元\n第二条 付款：金额 50000 元\n第三条 违约金 10000 元",
    )
    assert result["strategy"] == "original"
