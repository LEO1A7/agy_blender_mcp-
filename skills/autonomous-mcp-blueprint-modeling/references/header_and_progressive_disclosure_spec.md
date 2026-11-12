"""[REF_HEADER_SPEC] MCP 插件参考文档与代码案例库 6 行报文头渐进式披露规范
- 适用 (When): 全流程任意阶段快速检索 `examples/recipes/*.py`、`bin/*.py` 或 `examples/official_blender_mcp/` 官方库
- 用法 (How) : 先跑 `head -n 6 examples/recipes/case_*.py` 极速扫描报文头 (~150 tokens)，再决定直调/导入或切片深读
- 产出 (Out) : 保持主上下文洁净，零冗余算子常驻，按需精准提取算子或官方 MCP 工具源码
"""

# MCP 插件 6 行报文头与渐进式披露规范（Progressive Disclosure）

为保持主建模上下文绝对洁净，本插件所有自定义算子配方（`examples/recipes/case_r01`~`case_r08`）、标定/细部切片与拼图脚本（`bin/*.py`）、参考文档（`references/*.md`）以及官方 Blender MCP 库（`examples/official_blender_mcp/`，官方正文保持原样未动、仅在文件首部添加 6 行报文头）统一采用 **顶格 6 行报文头（`When / How / Out`）**：

## 1. 一键快筛报文头（零正文开销）

模型在建模全流程任意阶段可通过 `head -n 6` 快速阅读报文头，决定是否需要调用内部内容：

```bash
# 1. 快筛 8 个核心 CAD 配方、型材细部库、群组兜底与 N 面板 API 桥接案例：
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/recipes/case_r*.py

# 2. 快筛标尺网格标定、参考图高密细部切片与 Stage 4 多视图拼图工具：
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/bin/*.py

# 3. 快筛官方 Blender MCP 工具与指南报文头（官方正文零改动）：
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/official_blender_mcp/readme*
head -n 6 ~/.gemini/config/plugins/agy-autonomous-mcp-modeling-plugin/examples/official_blender_mcp/mcp/blmcp/tools/*.py
```

## 2. 三级按需消费策略

1. **级别 1（黑箱直调 / 函数导入）**：阅读 6 行报文头的 `用法 (How)` 后，直接在 `execute_blender_code` 中 `import` 对应函数或通过 CLI 执行脚本，**无需读取文件正文**。
2. **级别 2（局部切片读取）**：若需参考特定几何构造细节，使用 `read_file` 指定行号范围切片读取。
3. **级别 3（全文深读）**：仅在排查复杂拓扑或深度定制时读取全文。
