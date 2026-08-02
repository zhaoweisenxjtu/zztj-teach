---
name: zztj-teach
version: 0.1.3
description: >
  资治通鉴教学引擎。Agent 驱动的多模式历史教学系统。
  覆盖3种教学模式：导读（苏格拉底式逐段精读原文）、交互（决策模拟/多角色辩论/反事实推演）、
  生成（人物传记/事件分析/主题研究/考异溯源/社媒文案）。
  当用户要求讲解/教学/学习/分析资治通鉴相关历史内容时触发。
  也触发于讨论历史人物生平、政治斗争案例分析、战略决策模拟、原文导读等场景。
  Do NOT use when: 用户只是简单查询一个事实（应使用 zztj-query），
  或用户想要解读生成文章（应使用 zztj-reader）。
triggers:
  - 资治通鉴.*(教学|讲解|上课|学习)
  - (讲一下|讲讲|介绍).*(历史人物|人物|韩信|曹操|李世民|刘邦|项羽|汉武帝|诸葛亮)
  - (分析|复盘|解读).*(历史事件|事件|政治|斗争|政变|变法|战争)
  - (模拟|假如|假设|如果我是).*(决策|选择|场景|历史)
  - (导读|陪读|讲读|精读).*(原文|通鉴|资治通鉴|段落|卷)
  - 考异|史料.*(可信|真伪)|司马光.*(取舍|删选)
  - (变法|党争|宦官|外戚|谏诤|吏治).*(演变|历史|专题)
  - (辩论|论战|正反方).*(历史|王安石|变法)
  - (如果|万一|要是).*(当时|历史|没死|没输|赢了)
  - (改写|发公众号|小红书|文案|短视频).*(历史|通鉴|资治通鉴)
---

# 资治通鉴 教学引擎

自包含教学 skill。拷贝本目录到任意 Claude Code 实例即用。
所有路径相对于本 skill 根目录（`Path(__file__).parent`）。

## 数据工具

CLI 入口：本目录下 `zztj.py`（Python 标准库 + SQLite，零依赖）

| 命令 | 用途 | 示例 |
|------|------|------|
| `python zztj.py info` | 数据概览 | 总卷数、年代跨度、朝代分布 |
| `python zztj.py search <kw>` | 全文搜索（文言+白话） | `search "推恩令"` |
| `python zztj.py person <name>` | 人物出场记录 | `person "韩信"` |
| `python zztj.py timeline <name>` | 人物生平时间线 | `timeline "李世民"` |
| `python zztj.py contemporaries <name>` | 同时代人物 | `contemporaries "曹操"` |
| `python zztj.py year <y>` | 某年全部事件 | `year -206` |
| `python zztj.py range <s> <e>` | 时间段事件 | `range -206 -202` |
| `python zztj.py chapter <n>` | 按卷阅读全文 | `chapter 1` |
| `python zztj.py dynasty <name>` | 朝代概览 | `dynasty 唐` |
| `python zztj.py event [name]` | 关键事件（无参=列表） | `event "玄武门之变"` |
| `python zztj.py graph [name]` | 知识图谱查询 | `graph "刘邦"` |

图谱数据（可直接 Read）：
- `graph/entities.json` — 578 实体
- `graph/relations.json` — 1182 关系（6类型）
- `graph/force_evolution.json` — 75 势力演变
- `graph/event_chains.json` — 220 因果链
- `data/key_events.json` — 157 关键事件
- `data/concept_tags.json` — 6大类29子类概念标签

索引文件（可直接 Read）：
- `index/person_index.md` — 人物索引（按势力分组）
- `index/dynasty_timeline.md` — 朝代年表
- `index/graph_stats.md` — 图谱统计
- `index/key_events.md` — 关键事件列表
- `index/event_chains.md` — 事件因果链

## 全局约束（所有模式必须遵守）

执行任何教学模式前，将以下约束注入输出：

```
1. 三层分离：区分【史实】/【史论】/【演义】，显式标注
2. 原文引用：所有历史主张附出处 [卷X, XX纪, 公元前X年/公元X年]
3. 反事实标注：任何 what-if 推演标注"非史实推演"
4. 类比标注：现代迁移标注"现代类比"
5. 厚黑学防范：权谋分析包含制度/道德评价维度，不纯功利主义
6. 多源标注：Agent 补充内容标注"Agent知识，建议查考原典"
```

## 教学模式选择

根据用户意图自动选择模式。**三种模式**：

| 用户意图 | 模式 | 关键词 |
|---------|------|--------|
| 逐段学习原文 | `导读` | 导读/讲读/陪我读/精读/读原文 |
| 模拟决策/辩论/推演（需用户参与） | `交互` | 模拟/假如我是/辩论/正反方/如果XX没死 |
| 一次性产出完整文稿 | `生成` | 讲一下XX/分析XX事件/XX制度演变/改写发公众号 |

### 模式归类总览

| 新模式 | 合并的原模式 | 触发场景 |
|--------|-------------|---------|
| **导读** | 苏格拉底导读 `socratic_guide` | 逐段精读原文，苏格拉底式追问 |
| **交互** | 决策模拟 `decision_sim` + 多角色辩论 `multi_role_debate` + 反事实推演 `counterfactual` | 用户参与决策/辩论/推演 |
| **生成** | 人物传记 `biography` + 事件分析 `event_case` + 主题研究 `theme_study` + 考异溯源 `source_criticism` + 社媒文案 `social_draft` | 一次性产出完整文稿 |

---

## 模式 1：导读（苏格拉底式逐段精读）

**核心**：不直接给答案，逐层追问让学习者自己得出洞察。继承张居正《通鉴直解》传统。

### 第零步：查询已读进度 + 用户选段（启动必做）
```
Step 0a: Read teaching/progress.json            → 查询用户已读记录与当前阅读位置
Step 0b: 若存在已读记录：
          - 提示用户上次读到哪（卷号+段落主题+日期+定档）
          - 给出按通鉴时间顺序衔接的"下一段"建议
          - 询问用户：接着读下一段 / 换一段 / 指定新段落
Step 0c: 若用户指定新段落（或首次导读）：
          - 向用户呈现 3-5 个候选段落（每段一句话背景 + 涉及人物/事件）
          - 候选来源：search "上曰"/"上问"/"谏" + event 关键事件列表
          - 用户可从中选择，也可自行指定卷/关键词/人物
Step 0d: 用户选定后，进入"选段呈现"环节
```
选段优先含决策/冲突/对话的段落，不凭感觉挑。**用户有选段主动权**，AI 不得擅自替用户决定读哪段。

### 数据检索步骤
```
Step 1: python zztj.py chapter {n}              → 获取原文+译文
        或 python zztj.py search "{关键词}"     → 定位目标段落
Step 2: python zztj.py search "上曰" / "上问" / "谏"  → 发现含对话/决策/进谏的候选段落
Step 3: python zztj.py event                     → 关键事件列表，定位冲突/争论段落
Step 4: python zztj.py search "{相关概念}"       → （可选）补充相关段落
```

### 教学执行
```
Step 5: Read prompts/guide.md
Step 6: Agent 逐段导读（三维追问框架）：
        - 先抛开放问题探测用户水平，定档（初/中/高）
        - 呈现一段原文（完整展示，不限长度）+ 一句话背景
        - 第一层追问（事实层）：这段在说什么？XX为什么这么做？
        - 等待用户回答
        - 第二层追问（人性层）：他内心真正想要什么？暴露了什么性格/欲望/弱点？
        - 等待用户回答
        - 第三层追问（政治斗争层）：各方真正的利益？信息差在哪？司马光想警示什么？
        - 等待用户回答
        - 现实映射层：这个困境在现代职场/管理/人际里怎么对应？可迁移的底层逻辑？
        - 揭示：人性规律 + 政治逻辑 + 现实启示（标注【现代类比】）
        - 史学扩展阅读（AI 补充，不提问）：司马光剪裁/对照正史/资治目的，标注【Agent知识】
        - 进入下一段
        卡点熔断：某层答不上来→给提示→给译文→直接揭示，不硬推三层。
        长度约束：只限 AI 输出（追问≤150字、揭示≤400字、史学扩展≤200字），原文展示不限。
Step 7: Write teaching/guide/{YYYYMMDD}-{主题}.md
        文件头写入：用户定档结果 + 薄弱点（供下次同主题补强）
Step 8: 更新 teaching/index.json
Step 9: 更新 teaching/progress.json（记录已读位置 + 下一段建议，供下次启动查询）
```

### 导读关键约束
- 每次只推一层，不过度追问
- 追问基于原文，不是空泛的"你觉得呢"
- **主线聚焦人性/政治斗争/现实映射，不陷入史学考据**
- **现实映射偏实用（职场/管理/人际/决策），不做空泛思辨**
- **史学层由 AI 补充为扩展阅读，不向用户提问**
- 难度根据用户对古文的熟悉程度自动调整
- 定档后严格按档位走，不中途跳档

---

## 模式 2：交互（决策模拟 / 多角色辩论 / 反事实推演）

**核心**：用户深度参与。三种交互子模式，根据用户意图自动选择。

### 交互子模式选择

| 子模式 | 触发 | 核心 |
|--------|------|------|
| 决策模拟 | 模拟/假如我是/如果是你 | 站在历史角色立场做选择，对比真实历史 |
| 多角色辩论 | 辩论/正反方/XX该不该 | 还原历史辩论，用户站队/质疑 |
| 反事实推演 | 如果/万一/要是XX没死 | 严格约束下推演"如果变量改变" |

### 子模式 A：决策模拟

#### 数据检索步骤
```
Step 1: python zztj.py event "{name}"           → 事件详情
Step 2: python zztj.py year {time}              → 历史节点全貌
Step 3: for each 关键人物:
          python zztj.py person "{name}"        → 各方信息
```

#### 教学执行
```
Step 4: Read prompts/interact.md（决策模拟章节）
Step 5: Agent 执行5阶段交互式决策模拟：
        阶段1 — 情境设置（背景+角色+情报，隐藏结局）
        阶段2 — 决策呈现（3-4个可行方案）
        阶段3 — 等待用户选择
        阶段4 — 揭示历史真实结局，对比分析
        阶段5 — 复盘（司马光点评+长期影响+现代反思）
Step 6: 交互结束后 Write teaching/interact/{YYYYMMDD}-{事件名}-决策模拟.md
        保存完整的交互记录
Step 7: 更新 teaching/index.json
```

关键约束：
- 隐藏结局直到用户完成选择
- 情报范围等于历史角色的知识边界（不给上帝视角）
- 不预设"正确"答案

### 子模式 B：多角色辩论

#### 数据检索步骤
```
Step 1: python zztj.py event "{name}"             → 辩论事件背景+参与者
Step 2: for each 辩论参与方:
          python zztj.py person "{p}"             → 各方立场+言行记载
Step 3: python zztj.py year {time}                → 时代背景
Step 4: python zztj.py search "{关键词}"          → 补充相关言论记载
```

#### 教学执行
```
Step 5: Read prompts/interact.md（多角色辩论章节）
Step 6: Agent 扮演2-4个历史角色主持辩论：
        第一步 — 辩论议题设置（背景+核心议题+历史重要性）
        第二步 — 角色介绍（每个角色：身份/主张/论据（原文+译文）/动机）
        第三步 — 各方陈述（Agent以角色口吻轮流陈述）
        第四步 — 用户参与（站队/质疑/替代方案）
        第五步 — 揭示历史结果（采纳了谁的意见+结果+司马光评价）
        第六步 — 复盘讨论（信息不对称分析+现代类比）
Step 7: Write teaching/interact/{YYYYMMDD}-{事件}-辩论.md
Step 8: 更新 teaching/index.json
```

### 子模式 C：反事实推演

#### 数据检索步骤
```
Step 1: python zztj.py event "{name}"             → 事件详情和历史基线
Step 2: python zztj.py year {time}                → 历史节点全貌
Step 3: python zztj.py range {前2年} {后2年}       → 前后背景
Step 4: for each 关键人物:
          python zztj.py person "{p}"             → 人物行为模式参照
Step 5: python zztj.py search "{关键词}"          → 通鉴中类似情境的其他案例
```

#### 教学执行
```
Step 6: Read prompts/interact.md（反事实推演章节）
Step 7: Agent 执行反事实推演：
        第一步 — 理解用户的"如果"（要改变什么变量？预期是什么？）
        第二步 — 建立基线（真实历史+原文引用）
        第三步 — 约束条件分析（地理/制度/经济/人事/外部，哪些不变）
        第四步 — 推演第一步因果链（短/中期，标注【非史实推演】+可能性等级）
        第五步 — 推演第二步因果链（中/长期，标注不确定性增大）
        第六步 — 正史参照（通鉴中类似情境的实际结果）
        第七步 — 结论（可能性评估+揭示的结构性因素+对理解真实历史的启发）
Step 8: Write teaching/interact/{YYYYMMDD}-{事件}-反事实.md
Step 9: 更新 teaching/index.json
```

关键约束：
- 每次只改变一个变量
- 不超过两步因果链
- 所有推演标注 **【非史实推演】**
- 必须有正史类似情境作为参照

---

## 模式 3：生成（人物传记 / 事件分析 / 主题研究 / 考异溯源 / 社媒文案）

**核心**：一次性产出完整文稿。五种生成子模式，根据用户意图自动选择。

### 生成子模式选择

| 子模式 | 触发 | 核心 |
|--------|------|------|
| 人物传记 | 讲一下XX/介绍XX/XX是谁/生平 | 纵向重组人物一生+多源交叉验证 |
| 事件分析 | 分析/复盘/解读XX事件/XX之变 | 政治决策场景还原+利益格局分析 |
| 主题研究 | 变法史/党争史/XX制度演变 | 跨朝代对比+演变规律提炼 |
| 考异溯源 | 真的假的/史料可信/司马光为什么 | 史料取舍逻辑+批判性思维 |
| 社媒文案 | 改写/发公众号/小红书文案 | 教学文稿改写为平台文案 |

### 子模式 A：人物传记

#### 数据检索步骤
```
Step 1: python zztj.py person "{name}"         → 文言+白话全部出场记录
Step 2: python zztj.py timeline "{name}"        → 生平时间线（按卷排序）
Step 3: python zztj.py graph "{name}"           → 关系网（7种关系类型）
Step 4: python zztj.py contemporaries "{name}"  → 同时代人物列表
Step 5: python zztj.py event "{相关事件名}"      → （如该人物参与了已知关键事件）
```

#### 教学执行
```
Step 6: Read prompts/generate.md（人物传记章节）
Step 7: 以模板为 system prompt，以 Step1-5 结果为上下文，生成人物传记
Step 8: 多源交叉验证章节：利用训练数据补充以下内容，标注"Agent知识，建议查考[出处]原典"
        - 该人物在其他正史中的传记位置（史记/汉书/三国志等）
        - 通鉴记载与其他出处的显著差异
        - 后世史家的代表性评价
Step 9: Write teaching/generate/{YYYYMMDD}-{人名}-传记.md
Step 10: 更新 teaching/index.json
```

### 子模式 B：事件分析

#### 数据检索步骤
```
Step 1: python zztj.py event "{name}"           → 事件详情+参与者+类别+描述
Step 2: python zztj.py year {time}              → 事件年份全部上下文
Step 3: python zztj.py range {前2年} {后2年}     → 前后时代背景
Step 4: for each 关键参与者:
          python zztj.py person "{name}"        → 各方立场、资源、约束
Step 5: python zztj.py graph "{核心人物}"       → （可选）势力关系网
```

#### 教学执行
```
Step 6: Read prompts/generate.md（事件分析章节）
Step 7: Agent 输出完整的政治案例分析
Step 8: Write teaching/generate/{YYYYMMDD}-{事件名}-事件分析.md
Step 9: 更新 teaching/index.json
```

### 子模式 C：主题研究

#### 数据检索步骤
```
Step 1: python zztj.py search "{核心概念}"        → 全文检索该主题
Step 2: python zztj.py search "{相关概念2}"       → 补充检索（2-3轮）
Step 3: python zztj.py dynasty "{主要涉及的朝代}"  → 确认卷范围
Step 4: for each 代表性案例:
          python zztj.py event "{name}"           → 案例详情
          python zztj.py year {time}              → 案例年份上下文
Step 5: python zztj.py graph "{核心人物}"          → （可选）势力关系
```

#### 教学执行
```
Step 6: Read prompts/generate.md（主题研究章节）
Step 7: Agent 输出跨朝代主题研究：
        - 主题定义与时间分布
        - 3-5个典型案例（五维度分析：人事/制度/时机/利益/结果）
        - 跨朝代对比矩阵
        - 演变规律提炼（制度 vs 人事权重、路径依赖）
        - 司马光的整体立场
        - 现代镜鉴（标注【现代类比】）
Step 8: Write teaching/generate/{YYYYMMDD}-{主题}-主题研究.md
Step 9: 更新 teaching/index.json
```

### 子模式 D：考异溯源

#### 数据检索步骤
```
Step 1: python zztj.py chapter {n}                → 获取目标段落原文+译文
Step 2: python zztj.py search "{关键词}"          → 检索通鉴内其他相关记载
Step 3: python zztj.py event "{相关事件}"          → 事件的多方记载
Step 4: （可选）python zztj.py person "{人物}"     → 该人物在通鉴中的整体形象
```

#### 教学执行
```
Step 5: Read prompts/generate.md（考异溯源章节）
Step 6: Agent 执行考异溯源教学：
        第一步 — 呈现目标段落（原文+译文）
        第二步 — 引导发现（"这段有没有让你觉得奇怪的地方？"）
        第三步 — 揭示史料问题（其他出处的不同记载，标注【Agent知识，建议查考原典】）
        第四步 — 批判性讨论（司马光的取舍标准合理吗？）
        第五步 — 总结（史实/史论/存疑分层，方法论启示）
Step 7: Write teaching/generate/{YYYYMMDD}-{主题}-考异溯源.md
Step 8: 更新 teaching/index.json
```

### 子模式 E：社媒文案

#### 数据检索步骤
```
Step 1: Read teaching/index.json                  → 列出可改写文稿
Step 2: 用户选择文稿 + 目标平台
Step 3: Read 选中的教学文稿                       → 获取完整内容
```

#### 教学执行
```
Step 4: Read prompts/generate.md（社媒文案章节）
Step 5: Agent 执行改写：
        - 提取核心洞察（不超过5个核心要点）
        - 按目标平台格式改写：
          公众号（2000-3500字深度分析，标题+导语+正文+互动结尾）
          小红书（500-1000字要点体，emoji分段，口语化）
          短视频脚本（30/60/90秒口播，3秒钩子+5个反转+结尾引导）
        - 提供2-3个备选标题
        - 公众号版保留完整出处标注，小红书/短视频简化标注
Step 6: Write teaching/generate/{YYYYMMDD}-{标题}-{平台}-文案.md
Step 7: 更新 teaching/index.json
```

关键约束：
- 降低门槛，不降低深度——核心洞察不失真
- 史实区分：公众号保留三层标注；小红书/短视频简化为"据《资治通鉴》记载"
- 所有平台融入制度/道德评价维度，不做纯权谋解读

---

## 文稿保存与 index.json 更新

每次教学输出后，执行三步：

### 1. 保存文稿
路径：`teaching/{subdir}/{YYYYMMDD}-{slug}.md`

subdir 映射（三模式）：
- 导读 → `teaching/guide/`
- 交互 → `teaching/interact/`（文件名后缀区分子模式：决策模拟/辩论/反事实）
- 生成 → `teaching/generate/`（文件名后缀区分子模式：传记/事件分析/主题研究/考异溯源/文案）

文件头：
```markdown
---
mode: {导读|交互|生成}
submode: {子模式名}
topic: {主题}
date: {YYYY-MM-DD}
tags: [{标签1}, {标签2}, ...]
---
```

### 2. 更新 index.json

Read `teaching/index.json` → 追加 session 条目 → Write 回文件。

```json
{
  "session_id": "{YYYYMMDD}-{序号}",
  "mode": "{导读|交互|生成}",
  "submode": "{子模式名}",
  "topic": "{主题}",
  "path": "teaching/{subdir}/{文件名}.md",
  "tags": ["...", "..."],
  "created": "{ISO时间戳}"
}
```

序号规则：当天该模式下的第N篇（按 mode 分组计数 +1）。

### 3. 更新 progress.json（仅导读模式必做）

Read `teaching/progress.json` → 更新已读记录与当前阅读位置 → Write 回文件。

```json
{
  "version": "0.1.3",
  "last_read": {
    "date": "{YYYY-MM-DD}",
    "volume": {卷号},
    "topic": "{段落主题}",
    "level": "初|中|高",
    "path": "teaching/guide/{文件名}.md"
  },
  "history": [
    {
      "date": "{YYYY-MM-DD}",
      "volume": {卷号},
      "topic": "{段落主题}",
      "level": "初|中|高"
    }
  ],
  "next_suggestion": "{按通鉴时间顺序衔接的下一段建议}"
}
```

下次启动导读模式时，先 Read 此文件，提示用户上次读到哪，并给出 `next_suggestion` 引导按顺序精读。

---

## 数据规模参考

| 数据 | 规模 |
|------|------|
| 卷数 | 294 |
| 时间跨度 | 公元前403年 ~ 公元958年（1361年） |
| 时间段 | 1402 |
| 句子 | 30758 |
| 实体 | 578 |
| 关系 | 1182（7种类型：event/co_occurrence/same_power/opposition/lord_vassal/colleague/succession） |
| 关键事件 | 157 |
| 势力演变 | 75 |
| 因果链 | 220 |
| 种子实体 | 634 |
| 概念标签 | 6大类29子类 |
