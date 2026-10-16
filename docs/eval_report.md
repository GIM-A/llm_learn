# RAG 评测结果

> 本文档从 `scripts/evaluate.py` 末尾剪出。该段 Markdown 原先误粘在 `.py` 文件里（第 99 行起），
> 导致文件无法被 Python 解析（`SyntaxError: invalid character '，' (U+FF0C)` at line 102），见 CARD-1.6.1。
>
> ⚠️ 数据来源为**旧的离线评测链路**（`qwen-turbo` 生成 / 召回 top 20 / rerank top 10 / 私有 rerank 地址），
> 与当前线上链路（`qwen3.7-flash` / 召回 top 20 / rerank top 3）**不同源**，结论仅供参考。

## 测试集

- 20 道题，覆盖基础、中等、难题

## 三种策略对比

| 策略 | 准确率 |
|---|---|
| 纯向量检索 | 75% |
| 向量检索 + rerank（top 3） | 85% |
| 向量检索 + rerank（top 10） | 80% |

## 结论

- rerank 提升 10%
- top_n 太大反而降准
