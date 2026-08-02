# zztj-teach 评审问题清单

评审日期: 2026-07-31 | 总体评分: 8.2/10

## P0 (功能正确性/用户预期严重不符)

1. **zztj.py build-graph 硬编码 (1,68) 与宣传的294卷不符**
   - 文件: `zztj.py:381`
   - `bg(chapter_range=(1, 68))` 只构建周秦汉三代图谱
   - SKILL.md 宣传覆盖全294卷，但 CLI 入口行为与描述矛盾
   - 应改为 `(1, 294)` 或支持命令行参数指定范围

2. **timeline 命令的死代码**
   - 文件: `zztj.py:503-504`
   - `if len(rows) > 20 and ch_id > current_ch: break`
   - `ch_id > current_ch` 永远为 False（前面刚赋值 `current_ch = ch_id`）
   - 多出场人物的输出可能极长，意图实现的截断逻辑不生效

## P1 (教学输出质量/数据完整性/工程一致性)

3. **biography.md QA checklist 引用了不存在的关系类型名**
   - 文件: `prompts/biography.md` QA section
   - checklist 写的是 `monarch_minister`，但 enhance_graph 实际产出的类型是 `lord_vassal`
   - 另外 `colleague` 类型在 checklist 中未出现，部分关系会遗漏

4. **segment_tags 构建后未持久化**
   - 文件: `build_graph.py:88-120`
   - concept_stats 保存了，但 segment→tags 映射没有保存
   - 丢失了可做逐段标签搜索的能力

5. **build_graph 主入口和 CLI 入口行为不一致**
   - `build_graph.py __main__`: 调用 `build_graph(1, 294)` + `enhance_graph`
   - `zztj.py cmd_build_graph()`: 调用 `build_graph(1, 68)` + 不调用 enhance_graph
   - 两种方式产出的图谱数据完全不同

6. **source_criticism.md 预设案例表不完整**
   - 文件: `prompts/source_criticism.md`
   - "王安石变法"的卷范围写为"卷243-"，未填写结束卷号

7. **build_graph 和 enhance_graph 统计代码重复**
   - 两个文件都写 `graph_stats.md`
   - `build_index_files()` 和 `enhance_graph.py main()` 末尾做了相同的 degree 统计

## P2 (可靠性/可维护性/数据准确性)

8. **缺少 smoke test**
   - 无任何测试文件
   - 建议至少做: DB 连接成功、所有命令无语法错误、JSON 文件格式合法

9. **同名人物 disambiguation 缺失**
   - `name_index` 纯字符串匹配，不区分不同时代的同名人物
   - `year_override` 字段只修正年份，不用于实体消歧

10. **CLI 异常处理过于粗暴**
    - 文件: `zztj.py:763-765`
    - `raise` 会输出完整 traceback 给 LLM，干扰 token 预算
    - 建议改为 `sys.exit(1)` 或至少压缩错误信息

11. **命令行缺少子命令针对性 help**
    - 用户输入 `python zztj.py search` 无参数时，得到的是全量 HELP
    - 应给出该命令的用法提示

## P3 (增强项/体验优化)

12. **概念标签覆盖不足**
    - 文件: `data/concept_tags.json`
    - 当前 6 大类 29 子类，偏政治/制度
    - 缺少: 军事技术/战术、经济制度(赋税/货币/盐铁)、法律/刑罚、外交/朝贡

13. **is_emperor/is_minister 判定过于脆弱**
    - 文件: `enhance_graph.py:56-73`
    - 纯关键字子串匹配在 `llm_introduction` 中查找
    - intro 写法稍有变化就会漏判

14. **HOSTILE_POWERS 手工列表覆盖不全**
    - 文件: `enhance_graph.py:16-38`
    - 五代十国小国对立大量未覆盖，导致部分关系被错误标记为 co_occurrence
    - 重复条目: "北齐/北周"出现两次 (line 26, line 35)

15. **social_draft prompt 缺少出处标注的强制校验**
    - 文件: `prompts/social_draft.md`
    - 要求小红书/短视频标注"据《资治通鉴》记载"，但无强制检查点
    - QA checklist 应增加对应检查项

16. **prompt 文件缺少输出长度建议**
    - 所有 9 个 prompt 均无输出长度/耗时估计
    - 可能导致 token 耗尽或输出截断

17. **teaching/index.json 未经实际验证**
    - 当前 sessions 为空数组，读写流程是否为 0 错误状态无法确认
