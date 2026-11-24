# shanshuo — GRB 射电余辉星际闪烁（ISS）限制源尺度：可复现分析

学生工作Ⅱ的样本（43 个 GRB）用射电余辉的闪烁调制限制爆炸波尺度。本仓库把这套分析重做了一遍：
把两张 pptx 与十月那份结果 PDF 全部解析成结构化数据，用统一公式重算预测，交叉核对图里的读数，
并把结论写成一份可以直接讨论的意见。

- 结论与意见：`reports/审阅意见.md`
- 外部方法审阅：`reports/审查_方法链.md`
- 分组建议：`reports/分组建议.md`
- 验证锚点对照表（原文印刷值 + 逐面板读数）：`reports/验证锚点对照表.md`
- 逐面板对照表：`data/matched_table.csv`
- 样本清单（每个暴几页、几个面板、有无拟合页）：`data/bursts.csv`

## 数据从哪来

| 输入 | 位置 | 处理脚本 |
|---|---|---|
| 《闪烁分析样本.pptx》131 页 / 134 张图 / 130 条备注 | `../20261123/` | `scripts/extract_deck.py` → `data/sample/` |
| 《利用ISS来限制源尺度的理论以及初步样本.pptx》48 页 | `../20261123/` | 同上 → `data/theory/` |
| 《RISS19及NE2025模型的限制结果.pdf》313 行预测 | `../20261123/` | `scripts/parse_october.py` → `data/october_tables.json` |

备注里保留了学生的原始图路径与 SHA256（`data/sample/slides.json` 的 `notes` 字段），可以回溯到每一张画。

## 复现

```bash
# 0) 环境：python ≥3.11，只需 PIL；读图需要 ZHIPU_API_KEY（只走 glm-5.4）
python -m pip install pillow

# 1) 解 pptx（生成 slides.json 与逐页媒体）
python scripts/extract_deck.py "../20261123/闪烁分析样本.pptx" data/sample
python scripts/extract_deck.py "../20261123/利用ISS来限制源尺度的理论以及初步样本.pptx" data/theory

# 2) 读拟合图：每张图读三遍（整图/上半/下半），取多数一致值；有一遍常因裁剪返回 UNCLEAR，
#    故实际保证是「至少两遍独立读到同一个数」，矛盾的面板标 agree=false 不入结论
export ZHIPU_API_KEY=...          # 只有这一步需要网络与 key
python scripts/read_fits.py 4     # 4 个并发；遇到 HTTP 429 自动指数退避

# 3) 模型层自检 + 十月表解析与审计
python scripts/iss.py --test
python scripts/parse_october.py && python scripts/audit_october.py

# 4) 合并成对照表
python scripts/compare.py         # → data/matched_table.csv, data/compare_summary.json
```

`data/cache/` 是按「图像内容哈希 + 提问」缓存的模型回复，所以第 2 步重跑不再花钱、也不再触发限流；
要强制重读就删掉对应的缓存文件。`data/*/media/` 是解出来的图，随时可重建，不进版本库。

## 代码在做的事

- `iss.py`：Walker (1998) 关系，θ_F=8.11/√(νD) µas；强折射 θ_scatt=θ_F(ν0)(ν0/ν)^{11/5}、
  m_p=(ν/ν0)^{17/30}；弱散射 θ_scatt=θ_F(ν)；分辨源 m=m_p(θ_scatt/θ_s)^{7/6}；
  反解 θ_s=θ_scatt(m_p/m)^{6/7}（`m>m_p` 时拒绝反解）；角直径距离用 Planck18 平坦宇宙。
  `--test` 用 250702B Table 2 与 210702A Table 1 双向核对，包含 250702B 表内 3 GHz 行
  m=0.26 与 θ=5.67 µas 不自洽（需 m≈0.30）的记录。
- `read_fits.py`：只调 `glm-5.4`，三遍交叉核对；不一致的记 `agree=false` 并保留三份原始文本，不取平均。
- `parse_october.py` / `audit_october.py`：把 PDF 表格解析成行，然后检查三件事——
  实测列是否随模型变、预测列能否由 SM/ν0/Dsc 复算、Size 是否等于 D_A·θ_scatt。
- `compare.py`：把面板读数与十月预测按频率匹配（单频 10% 容差；宽频箱内所有频率都匹配并标 `band`），
  算出 `fvar_over_mp`，并给每行一个 `verdict`：
  `fit_failed`（χ²_red>10）/ `incompatible`（F_var≥m_p）/ `ceiling`（0.7≤比值<1）/ `invertible`（0.15<比值<0.7，
  单频、读数一致、拟合合格，此时才填 `theta_s_uas` 与 `size_inv_1e16cm`）/ `dilute`（≤0.15）/ `unresolved` /
  `not_detected` / `data_only` / `no_prediction`。
  同时输出 `data/size_consistency.json`：同一暴各频率反解的 θ_s 必须一致，否则说明 F_var 不是纯闪烁调制。
- `size_consistency.json` 里 5 个能做检验的暴全部不过（θ_s 相差 3.3–17.7 倍），这是本次重做最硬的一条发现。

## 已知限制

- 图里的数字来自大模型读图。两/三遍一致只保证「读得稳」，不等于「读得对」；关键数值请对照原图复核。
- `read_fits.py` 的三遍里常有一遍返回 UNCLEAR（裁剪没覆盖到框），175/214 个面板因此只有两遍给出数值。
- 43 个暴里有 3 个没有拟合页（980329、130427A、160625B），本仓库不替它们补数。
- 十月那份 PDF 的实测列与本次 F_var 不是同一个统计量，两者的差异在 `reports/审阅意见.md` 第二节有专门讨论。
- `iss.py --test` 的 250702B 行把原文 θ_F=0.5 µas 当输入再用它反推 D_scr，是循环论证（见 `reports/审查_方法链.md`）；
  它只说明代数自洽，不说明原文数值物理自洽。
- `reports/分组建议.md` 与 `data/classification_draft.json` 是审阅模型按旧版 `matched_table`（可反演 53 行）生成的草案，
  文首已加快照说明；按暴分组仍可用，E 级请按新 `verdict` 列重读。
