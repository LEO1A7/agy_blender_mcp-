"""[REF_HEADER_SPEC] MCP 插件参考文档与代码案例库 6 行报文头渐进式披露规范
- 适用 (When): 全流程任意阶段快速检索 `examples/recipes/*.py`、`bin/*.py` 或 `references/*.md`（含官方 26 工具字典）
- 用法 (How) : 先跑 `head -n 6` 极速扫描报文头 (~150 tokens)，再决定直调/导入或切片深读
- 产出 (Out) : 保持主上下文洁净，零冗余算子常驻，按需精准提取算子或官方 MCP 工具说明书
"""

# MCP 插件 6 行报文头与渐进式披露规范（Progressive Disclosure）

为保持主建模上下文绝对洁净，本插件所有自定义算子配方（`examples/recipes/case_r01`~`case_r11`）、标定/细部切片与拼图脚本（`bin/*.py`）以及参考文档（`references/*.md`，含 `official_mcp_tools_and_prompts.md`）统一采用 **顶格 6 行报文头（`When / How / Out`）**；官方内嵌仓库 `examples/official_blender_mcp/` 保持 100% 原样未动：

## 1. 一键快筛报文头（零正文开销）

模型在建模全流程任意阶段可通过 `head -n 6` 快速阅读报文头，决定是否需要调用内部内容：

```bash
# 1. 快筛 11 个核心 CAD/Spec/剖切配方与 N 面板 API 桥接案例：
head -n 6 ~/.gemini/config/plugins/abmcp/examples/recipes/case_r*.py

# 2. 快筛平面转正、剖面标高、网格标定、参考图细部切片、剖切叠加与拼图工具：
head -n 6 ~/.gemini/config/plugins/abmcp/bin/*.py

# 3. 快筛参考文档（含官方 MCP 26 工具参数字典与 prompts.yml 规范）：
head -n 6 ~/.gemini/config/plugins/abmcp/skills/autonomous-mcp-blueprint-modeling/references/*.md
```

## 2. 三级按需消费策略

1. **级别 1（黑箱直调 / 函数导入）**：阅读 6 行报文头的 `用法 (How)` 后，直接调用官方 MCP 工具或在 `execute_blender_code` 中 `import` 对应函数 / 通过 CLI 执行脚本，**无需读取文件正文**。
2. **级别 2（局部切片读取）**：若需参考特定几何构造细节，使用 `read_file` 指定行号范围切片读取。
3. **级别 3（全文深读）**：仅在排查复杂拓扑或深度定制时读取全文。
