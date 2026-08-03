#!/usr/bin/env python3
"""资治通鉴 知识图谱构建器 v2 — 种子实体 + 全文匹配 + 关系推理"""

import sqlite3
import sys
import json
import re
from pathlib import Path
from collections import defaultdict, Counter

DB_PATH = Path(__file__).parent / "zztjdata.db"
GRAPH_DIR = Path(__file__).parent / "graph"
DATA_DIR = Path(__file__).parent / "data"

# ============ 种子实体加载 ============
# 从 data/seed_entities.json 读取，手工维护，与代码分离
def _load_seed_entities():
    seed_file = DATA_DIR / "seed_entities.json"
    if seed_file.exists():
        return json.loads(seed_file.read_text(encoding="utf-8"))
    print("警告: seed_entities.json 不存在，使用空列表")
    return []

SEED_ENTITIES = _load_seed_entities()


def build_graph(chapter_range=(1, 68)):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 1. 构建种子实体字典
    entities = {}
    name_index = {}  # 所有可能的名字 -> 规范名
    for e in SEED_ENTITIES:
        name = e["name"]
        entities[name] = {
            "name": name,
            "alias": e.get("alias", []),
            "power": e["power"],
            "llm_introduction": e["intro"],
            "first_appear": None,
            "last_appear": None,
            "first_chapter": None,
            "mention_count": 0,
            "year_override": e.get("year_override"),  # 手工覆盖年份
        }
        name_index[name] = name
        for alias in e.get("alias", []):
            name_index[alias] = name

    # 2. 扫描全文，匹配种子实体
    c.execute("""SELECT c.title, c.id as ch_id,
                        s.id as seg_id, s.chapter_id, s.seq,
                        s.time_original, s.time_translated,
                        sen.original, sen.translated
                 FROM sentences sen
                 JOIN segments s ON sen.segment_id = s.id
                 JOIN chapters c ON s.chapter_id = c.id
                 WHERE c.id BETWEEN ? AND ?
                 ORDER BY s.id, sen.seq""",
              chapter_range)

    # 加载年份索引
    year_file = DATA_DIR / "segment_year_index.json"
    seg_years = {}
    if year_file.exists():
        yi = json.loads(year_file.read_text(encoding="utf-8"))
        for key, seg in yi["segments"].items():
            seg_years[(seg["juan_index"], seg["segment_index"])] = seg["year"]

    rows = c.fetchall()
    total = len(rows)
    print(f"扫描卷{chapter_range[0]}-{chapter_range[1]}，共 {total} 条...")

    # 加载概念标签
    tags_file = DATA_DIR / "concept_tags.json"
    tag_keywords = {}  # category -> [(subtag, compiled_regex)]
    if tags_file.exists():
        tags_data = json.loads(tags_file.read_text(encoding="utf-8"))
        for cat_name, cat_info in tags_data["categories"].items():
            tag_keywords[cat_name] = {}
            for sub_name, kws in cat_info["subtags"].items():
                if kws:
                    tag_keywords[cat_name][sub_name] = re.compile("|".join(re.escape(k) for k in kws))

    # 按 segment 分组统计
    segment_persons = defaultdict(set)  # seg_id -> {canonical_names}
    segment_tags = defaultdict(set)     # seg_id -> {tag_strings}
    concept_stats = Counter()           # "category|subtag" -> count

    for i, row in enumerate(rows):
        if i % 2000 == 0:
            print(f"  {i}/{total} ({100*i//total}%)")

        text = (row["translated"] or "") + (row["original"] or "")
        seg_key = (row["chapter_id"], row["seq"])

        seg_id = f"{row['chapter_id']}-{row['seq']}"
        for search_name, canonical in name_index.items():
            if search_name in text:
                entities[canonical]["mention_count"] += 1
                segment_persons[seg_id].add(canonical)

                # 记录首次出现和最后出现
                e = entities[canonical]
                year = seg_years.get(seg_key)
                if e["first_appear"] is None:
                    e["first_appear"] = str(year) if year else None
                    e["first_chapter"] = row["title"]
                if year is not None:
                    e["last_appear"] = str(year)  # 持续更新

        # 概念标签匹配（每句只检查一次）
        for cat_name, subtags in tag_keywords.items():
            for sub_name, pattern in subtags.items():
                if pattern.search(text):
                    tag_str = f"{cat_name}|{sub_name}"
                    segment_tags[seg_id].add(tag_str)
                    concept_stats[tag_str] += 1

    print(f"  {total}/{total} (100%)")

    # 2.5 应用年份覆盖（手工修正误匹配），保留 year_override 用于审计
    override_count = 0
    for e in entities.values():
        ov = e.get("year_override")
        if ov is not None and e["first_appear"] is not None:
            e["first_appear"] = str(ov)
            override_count += 1
        if ov is None:
            e["year_override"] = None
    if override_count:
        print(f"  年份覆盖: {override_count} 个实体")

    # 3. 构建关系：基于共现（带年代过滤）
    cooccurrence = Counter()
    for seg_id, persons in segment_persons.items():
        persons_list = sorted(persons)
        for i in range(len(persons_list)):
            for j in range(i + 1, len(persons_list)):
                pair = (persons_list[i], persons_list[j])
                cooccurrence[pair] += 1

    # 4. 关系去噪：过滤跨时代共现
    def _year_int(val):
        """将年份字符串转为整数，无法转换返回None"""
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    degree = Counter()
    relations = []
    filtered_count = 0
    for (a, b), count in cooccurrence.most_common(1000):
        degree[a] += 1
        degree[b] += 1
        if count >= 3:  # 至少共现3次的才纳入关系
            # 年代过滤：使用 first_appear 作为活跃年代锚点
            # 活跃窗口 = first_appear 前后各30年（共60年窗口）
            # 如果两人活跃窗口完全不重叠且差距>100年，判定为跨时代伪共现
            ea = entities.get(a)
            eb = entities.get(b)
            if ea and eb:
                first_a = _year_int(ea.get("first_appear"))
                first_b = _year_int(eb.get("first_appear"))
                if first_a is not None and first_b is not None:
                    gap = abs(first_a - first_b)
                    if gap > 150:  # first_appear 差距超过150年
                        filtered_count += 1
                        continue
            relations.append({
                "from": [a],
                "to": [b],
                "action": "共现",
                "context": f"在{count}个时间段中共同出现",
                "time": None,
                "event_name": None,
                "location": None,
                "weight": count,
            })

    # 5. 加载手工标注关系（demo_er.json + key_events.json）
    demo_file = DATA_DIR / "demo_er.json"
    if demo_file.exists():
        demo = json.loads(demo_file.read_text(encoding="utf-8"))
        for r in demo.get("relations", []):
            relations.append(r)

    events_file = DATA_DIR / "key_events.json"
    event_relations = 0
    if events_file.exists():
        events = json.loads(events_file.read_text(encoding="utf-8"))
        for ev in events:
            participants = ev.get("participants", [])
            # 为每个事件的参与者在 entities 中生成两两关系
            for i in range(len(participants)):
                for j in range(i + 1, len(participants)):
                    a, b = participants[i], participants[j]
                    if a in entities and b in entities:
                        relations.append({
                            "from": [a],
                            "to": [b],
                            "action": "参与事件",
                            "event_name": ev["name"],
                            "context": ev["description"],
                            "time": str(ev["time"]),
                            "location": ev.get("location"),
                            "category": ev.get("category"),
                            "weight": 5,
                        })
                        event_relations += 1
        print(f"  加载事件: {len(events)} 条，生成 {event_relations} 条事件关系")

    # 只保留有出场的实体
    entities_list = [e for e in entities.values() if e["mention_count"] > 0]
    entities_list.sort(key=lambda x: -x["mention_count"])

    # 保存
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    (GRAPH_DIR / "entities.json").write_text(
        json.dumps(entities_list, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (GRAPH_DIR / "relations.json").write_text(
        json.dumps(relations, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (GRAPH_DIR / "concept_stats.json").write_text(
        json.dumps([{"tag": t, "count": c} for t, c in concept_stats.most_common()], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    # 逐段标签映射持久化，支持按段检索概念（P1-4）
    (GRAPH_DIR / "segment_tags.json").write_text(
        json.dumps({seg: sorted(tags) for seg, tags in sorted(segment_tags.items())},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    conn.close()

    # 统计
    powers = Counter(e["power"] for e in entities_list)
    print(f"\n=== 知识图谱构建完成 ===")
    print(f"实体数: {len(entities_list)}（共 {len(SEED_ENTITIES)} 个种子）")
    print(f"关系数: {len(relations)}（过滤 {filtered_count} 条跨时代共现）")
    print(f"\n势力分布:")
    for p, c in powers.most_common(20):
        print(f"  {p}: {c}人")
    print(f"\n概念标签分布:")
    for tag, cnt in concept_stats.most_common(12):
        print(f"  {tag}: {cnt}次")

    print(f"\nTop 30 高频人物:")
    for e in entities_list[:30]:
        aliases = f" ({', '.join(e['alias'])})" if e.get("alias") else ""
        print(f"  {e['name']}{aliases}: {e['mention_count']}次 | {e['power']} | {e.get('first_appear', '?')}")

    return entities_list, relations


def write_graph_stats(entities, relations, index_dir=None):
    """写图统计 Markdown（含关系类型分布），供 build 与 enhance 复用（P1-7）"""
    index_dir = index_dir or GRAPH_DIR.parent / "index"
    degree = Counter()
    for r in relations:
        for f in (r.get("from") or []):
            degree[f] += 1
        for t in (r.get("to") or []):
            degree[t] += 1

    lines = ["# 知识图谱统计\n", f"- 实体: {len(entities)}", f"- 关系: {len(relations)}",
             "\n## 关系类型分布\n"]
    type_counts = Counter(r.get("relation_type") or r.get("action", "共现") for r in relations)
    for t, c in type_counts.most_common():
        lines.append(f"- {t}: {c}条")
    lines.append("\n## 关联最广的人物 (Top 30)\n")
    for name, d in degree.most_common(30):
        lines.append(f"- {name}: {d}条关联")

    (index_dir / "graph_stats.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"图统计: {index_dir / 'graph_stats.md'}")


def build_index_files():
    entities_file = GRAPH_DIR / "entities.json"
    relations_file = GRAPH_DIR / "relations.json"

    if not entities_file.exists():
        print("请先运行 build_graph")
        return

    entities = json.loads(entities_file.read_text(encoding="utf-8"))
    relations = json.loads(relations_file.read_text(encoding="utf-8"))

    index_dir = Path(__file__).parent / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    # 人物索引
    by_power = defaultdict(list)
    for e in entities:
        p = e.get("power", "未知")
        by_power[p].append(e)

    lines = ["# 资治通鉴 人物索引\n", f"覆盖全294卷（周秦汉魏晋南北朝隋唐五代），共 {len(entities)} 人\n"]
    for power in sorted(by_power.keys(), key=lambda p: -len(by_power[p])):
        lines.append(f"\n## {power} ({len(by_power[power])}人)\n")
        for e in sorted(by_power[power], key=lambda x: -x.get("mention_count", 0)):
            aliases = f"（{'、'.join(e['alias'])}）" if e.get("alias") else ""
            intro = e.get("llm_introduction", "")
            first = f"，首次出现: {e['first_appear']}" if e.get("first_appear") else ""
            lines.append(f"- **{e['name']}**{aliases}: {intro}{first}（{e['mention_count']}次）")

    (index_dir / "person_index.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"人物索引: {index_dir / 'person_index.md'}")

    # 朝代年表
    dynasty_map = {"周": (1, 5), "秦": (6, 8), "汉": (9, 68), "魏": (69, 78), "晋": (79, 118),
                   "宋": (119, 134), "齐": (135, 144), "梁": (145, 166), "陈": (167, 176),
                   "隋": (177, 184), "唐": (185, 268), "五代": (269, 294)}
    year_file = DATA_DIR / "juan_year_index.json"
    lines = ["# 资治通鉴 朝代年表\n", "周秦汉魏晋南北朝隋唐五代\n"]
    if year_file.exists():
        yi = json.loads(year_file.read_text(encoding="utf-8"))
        for name, (start, end) in dynasty_map.items():
            ys = yi["juan_start_year"].get(str(start))
            ye = yi["juan_start_year"].get(str(end))
            ysl = f"公元前{abs(ys)}" if ys and ys < 0 else f"公元{ys}" if ys else "?"
            yel = f"公元前{abs(ye)}" if ye and ye < 0 else f"公元{ye}" if ye else "?"
            lines.append(f"- **{name}**: 卷{start}-{end}，{ysl} ~ {yel}")

    (index_dir / "dynasty_timeline.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"朝代年表: {index_dir / 'dynasty_timeline.md'}")

    # 图统计（复用公共函数，P1-7）
    write_graph_stats(entities, relations, index_dir)

    # 关键事件
    events = [r for r in relations if r.get("event_name")]
    if events:
        lines = ["# 资治通鉴 关键事件\n"]
        for r in sorted(events, key=lambda x: x.get("time") or ""):
            lines.append(f"- **{r.get('time', '?')}** {r.get('event_name')}: {r.get('context', '')}")
        (index_dir / "key_events.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"关键事件: {index_dir / 'key_events.md'}")

    # 概念标签索引
    concept_file = GRAPH_DIR / "concept_stats.json"
    if concept_file.exists():
        stats = json.loads(concept_file.read_text(encoding="utf-8"))
        lines = ["# 资治通鉴 概念标签分布\n", f"共 {len(stats)} 个标签\n"]
        by_cat = defaultdict(list)
        for s in stats:
            cat, sub = s["tag"].split("|")
            by_cat[cat].append((sub, s["count"]))
        for cat in sorted(by_cat.keys()):
            lines.append(f"\n## {cat}\n")
            for sub, cnt in sorted(by_cat[cat], key=lambda x: -x[1]):
                lines.append(f"- **{sub}**: {cnt}条")
        (index_dir / "concept_index.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"概念标签: {index_dir / 'concept_index.md'}")


if __name__ == "__main__":
    print("=== 资治通鉴知识图谱构建 v2 ===\n")
    build_graph(chapter_range=(1, 294))
    print()
    build_index_files()
    print()
    # 图谱增强：关系类型化 + 势力演变 + 事件因果链
    try:
        from enhance_graph import main as enhance_main
        enhance_main()
    except ImportError:
        print("提示: enhance_graph.py 未找到，跳过硬编码增强")
