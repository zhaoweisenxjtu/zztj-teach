#!/usr/bin/env python3
"""资治通鉴 CLI 查询工具。用法: python zztj.py <command> [args]"""

import sqlite3
import sys
import os
import json
from pathlib import Path
from collections import defaultdict

# 确保 stdout 使用 UTF-8 编码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = Path(__file__).parent / "zztjdata.db"
CHAPTER_DIR = Path(__file__).parent / "chapters"
GRAPH_DIR = Path(__file__).parent / "graph"
ROOT = Path(__file__).parent

# --- 朝代映射 ---
DYNASTY_MAP = {
    "周": (1, 5), "秦": (6, 8), "汉": (9, 68),
    "魏": (69, 78), "晋": (79, 118), "宋": (119, 134),
    "齐": (135, 144), "梁": (145, 166), "陈": (167, 176),
    "隋": (177, 184), "唐": (185, 268), "五代": (269, 294),
}


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ---------- commands ----------

def cmd_info():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM chapters")
    total_chapters = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM segments")
    total_segments = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sentences")
    total_sentences = c.fetchone()[0]

    # year span from year index
    year_file = Path(__file__).parent / "data" / "juan_year_index.json"
    years = None
    if year_file.exists():
        yi = json.loads(year_file.read_text(encoding="utf-8"))
        years = yi.get("juan_start_year", {})

    print(f"## 资治通鉴 数据概览\n")
    print(f"- 总卷数: {total_chapters}")
    print(f"- 时间段: {total_segments}")
    print(f"- 句子数: {total_sentences}")
    if years:
        y_vals = [int(v) for v in years.values()]
        min_y = min(y_vals)
        max_y = max(y_vals)
        if min_y < 0:
            span_str = f"公元前{abs(min_y)}年 ~ 公元{max_y}年 ({abs(min_y) + max_y}年)"
        else:
            span_str = f"公元{min_y}年 ~ 公元{max_y}年 ({max_y - min_y}年)"
        print(f"- 时间跨度: {span_str}")

    print(f"\n## 朝代分布\n")
    for name, (start, end) in DYNASTY_MAP.items():
        c.execute("SELECT COUNT(*) FROM chapters WHERE id BETWEEN ? AND ?", (start, end))
        count = c.fetchone()[0]
        print(f"- {name}: {count}卷 (卷{start}-{end})")

    # Graph stats
    if GRAPH_DIR.exists():
        entities_file = GRAPH_DIR / "entities.json"
        relations_file = GRAPH_DIR / "relations.json"
        if entities_file.exists():
            ents = json.loads(entities_file.read_text(encoding="utf-8"))
            print(f"\n## 知识图谱\n- 实体数: {len(ents)}")
        if relations_file.exists():
            rels = json.loads(relations_file.read_text(encoding="utf-8"))
            print(f"- 关系数: {len(rels)}")

    conn.close()


def cmd_search(keyword, max_results=10):
    conn = get_db()
    c = conn.cursor()
    query = """
        SELECT c.title, s.time_original, sen.original, sen.translated, c.id as ch_id
        FROM sentences sen
        JOIN segments s ON sen.segment_id = s.id
        JOIN chapters c ON s.chapter_id = c.id
        WHERE sen.original LIKE ? OR sen.translated LIKE ?
        ORDER BY s.id
        LIMIT ?
    """
    like = f"%{keyword}%"
    c.execute(query, (like, like, max_results))
    rows = c.fetchall()
    for r in rows:
        print(f"### [{r['title']}] {r['time_original'] or ''}")
        print(f"> {r['original'][:120]}")
        print(f"> {r['translated'][:120]}")
        print()
    print(f"({len(rows)} 条结果，关键词: {keyword})")
    conn.close()


def cmd_person(name, max_results=15):
    conn = get_db()
    c = conn.cursor()
    query = """
        SELECT c.title, s.time_original, sen.original, sen.translated, c.id as ch_id
        FROM sentences sen
        JOIN segments s ON sen.segment_id = s.id
        JOIN chapters c ON s.chapter_id = c.id
        WHERE sen.translated LIKE ? OR sen.original LIKE ?
        ORDER BY s.id
        LIMIT ?
    """
    like = f"%{name}%"
    c.execute(query, (like, like, max_results))
    rows = c.fetchall()
    if not rows:
        print(f"未找到人物「{name}」")
        conn.close()
        return
    for r in rows:
        print(f"### [{r['title']}] {r['time_original'] or ''}")
        print(f"> {r['original'][:150]}")
        print(f"> {r['translated'][:150]}")
        print()
    print(f"({len(rows)} 条结果，人物: {name})")
    conn.close()


def cmd_year(year):
    conn = get_db()
    c = conn.cursor()

    # Find segments matching the year via year index
    year_file = Path(__file__).parent / "data" / "segment_year_index.json"
    if not year_file.exists():
        print("年份索引文件不存在")
        conn.close()
        return

    yi = json.loads(year_file.read_text(encoding="utf-8"))
    matching = []
    for key, seg in yi["segments"].items():
        if seg["year"] == year:
            matching.append((seg["juan_index"], seg["segment_index"]))

    if not matching:
        print(f"公元{year}年无记录" if year >= 0 else f"公元前{abs(year)}年无记录")
        conn.close()
        return

    year_label = f"公元{year}年" if year >= 0 else f"公元前{abs(year)}年"
    print(f"## {year_label}\n")

    for juan_idx, seg_idx in matching:
        c.execute("""SELECT s.time_original, s.time_translated, sen.original, sen.translated
                     FROM segments s
                     JOIN sentences sen ON s.id = sen.segment_id
                     WHERE s.chapter_id = ? AND s.seq = ?
                     ORDER BY sen.seq""", (juan_idx, seg_idx))
        rows = c.fetchall()
        c2 = conn.cursor()
        c2.execute("SELECT title FROM chapters WHERE id = ?", (juan_idx,))
        ch_title = c2.fetchone()[0]
        for r in rows:
            print(f"**[{ch_title}] {r['time_original'] or ''}**")
            print(f"> {r['original'][:200]}")
            print(f"> {r['translated'][:200]}")
            print()

    print(f"(共 {len(matching)} 个时段)")
    conn.close()


def cmd_range(start_year, end_year):
    conn = get_db()
    c = conn.cursor()

    year_file = Path(__file__).parent / "data" / "segment_year_index.json"
    if not year_file.exists():
        print("年份索引文件不存在")
        conn.close()
        return

    yi = json.loads(year_file.read_text(encoding="utf-8"))
    matching = []
    for key, seg in yi["segments"].items():
        if seg["year"] and start_year <= seg["year"] <= end_year:
            matching.append((seg["juan_index"], seg["segment_index"], seg["year"]))

    if not matching:
        print(f"{start_year}~{end_year}年间无记录")
        conn.close()
        return

    print(f"## {start_year}年 ~ {end_year}年 ({len(matching)}个时段)\n")

    for juan_idx, seg_idx, year in matching[:50]:  # limit to 50
        c.execute("""SELECT s.time_original, s.time_translated, sen.original, sen.translated
                     FROM segments s
                     JOIN sentences sen ON s.id = sen.segment_id
                     WHERE s.chapter_id = ? AND s.seq = ?
                     ORDER BY sen.seq LIMIT 3""", (juan_idx, seg_idx))
        rows = c.fetchall()
        c2 = conn.cursor()
        c2.execute("SELECT title FROM chapters WHERE id = ?", (juan_idx,))
        ch_title = c2.fetchone()[0]
        year_label = f"公元{year}年" if year >= 0 else f"公元前{abs(year)}年"
        print(f"### {year_label} — [{ch_title}]")
        for r in rows:
            print(f"> {r['translated'][:150]}")
        print()

    if len(matching) > 50:
        print(f"(仅显示前50个时段，共{len(matching)}个)")
    conn.close()


def cmd_chapter(ch_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT title FROM chapters WHERE id = ?", (ch_id,))
    row = c.fetchone()
    if not row:
        print(f"卷{ch_id}不存在")
        conn.close()
        return

    print(f"# {row['title']}\n")

    c.execute("""SELECT s.seq, s.time_original, s.time_translated, sen.original, sen.translated
                 FROM segments s
                 JOIN sentences sen ON s.id = sen.segment_id
                 WHERE s.chapter_id = ?
                 ORDER BY s.seq, sen.seq""", (ch_id,))
    rows = c.fetchall()
    for r in rows:
        if r['time_original']:
            print(f"## {r['time_original']}")
        print(f"{r['original']}")
        print(f"{r['translated']}")
        print()

    conn.close()


def cmd_dynasty(name):
    if name not in DYNASTY_MAP:
        print(f"未知朝代: {name}")
        print(f"可用: {', '.join(DYNASTY_MAP.keys())}")
        return

    start, end = DYNASTY_MAP[name]
    conn = get_db()
    c = conn.cursor()

    # Get summary
    c.execute("""SELECT c.title, COUNT(DISTINCT s.id) as seg_count
                 FROM chapters c JOIN segments s ON c.id = s.chapter_id
                 WHERE c.id BETWEEN ? AND ?
                 GROUP BY c.id ORDER BY c.id""", (start, end))
    rows = c.fetchall()

    # Year span
    year_file = Path(__file__).parent / "data" / "juan_year_index.json"
    years = {}
    if year_file.exists():
        yi = json.loads(year_file.read_text(encoding="utf-8"))
        for k, v in yi["juan_start_year"].items():
            ki = int(k)
            if start <= ki <= end:
                years[ki] = v

    print(f"## {name}纪 ({start}-{end}卷)\n")

    if years:
        y_vals = [v for v in years.values() if v is not None]
        if y_vals:
            y_min = min(y_vals)
            y_max = max(y_vals)
            l1 = f"公元前{abs(y_min)}年" if y_min < 0 else f"公元{y_min}年"
            l2 = f"公元前{abs(y_max)}年" if y_max < 0 else f"公元{y_max}年"
            print(f"时间: {l1} ~ {l2}")

    print(f"\n| 卷 | 标题 | 时段数 |")
    print(f"|-----|------|--------|")
    for r in rows:
        print(f"| {start} | {r['title']} | {r['seg_count']} |")
        start += 1

    conn.close()


def cmd_graph(query=None):
    """查询知识图谱"""
    if not GRAPH_DIR.exists():
        print("知识图谱尚未构建")
        return

    entities_file = GRAPH_DIR / "entities.json"
    relations_file = GRAPH_DIR / "relations.json"

    if not entities_file.exists():
        print("实体数据不存在")
        return

    entities = json.loads(entities_file.read_text(encoding="utf-8"))
    relations = json.loads(relations_file.read_text(encoding="utf-8")) if relations_file.exists() else []

    if query:
        # Search entities by name
        results = [e for e in entities if query in e.get("name", "")]
        if not results:
            # Search aliases
            results = [e for e in entities if any(query in a for a in e.get("alias", []))]
        if not results:
            print(f"未找到实体: {query}")
            return

        for e in results:
            print(f"## {e['name']}")
            if e.get("alias"):
                print(f"别名: {', '.join(e['alias'])}")
            if e.get("power"):
                print(f"势力: {e['power']}")
            if e.get("llm_introduction"):
                print(f"简介: {e['llm_introduction']}")
            if e.get("first_appear"):
                print(f"首次出现: {e['first_appear']}")

            # Find relations involving this entity
            RELATION_TYPE_LABEL = {
                "event": "参与事件",
                "co_occurrence": "共现",
                "same_power": "同势力",
                "opposition": "敌对",
                "lord_vassal": "君臣",
                "succession": "继承",
                "colleague": "同僚",
            }
            related = [r for r in relations if e['name'] in r.get('from', []) or e['name'] in r.get('to', [])]
            if related:
                related.sort(key=lambda x: -(x.get('weight', 0)))
                print(f"\n相关人物 (Top {min(15, len(related))}):")
                shown = 0
                for r in related:
                    if shown >= 15:
                        break
                    if e['name'] in r.get('from', []):
                        others = [n for n in r.get('to', []) if n != e['name']]
                    else:
                        others = [n for n in r.get('from', []) if n != e['name']]
                    if others:
                        w = r.get('weight', 1)
                        rt = r.get('relation_type')
                        label = RELATION_TYPE_LABEL.get(rt, r.get("action", "共现"))
                        print(f"  - {', '.join(others[:3])} ({w}次，{label})")
                        shown += 1
            print()
    else:
        # Overview
        powers = {}
        for e in entities:
            p = e.get("power", "未知")
            powers[p] = powers.get(p, 0) + 1

        print("## 知识图谱概览\n")
        print(f"- 实体总数: {len(entities)}")
        print(f"- 关系总数: {len(relations)}")
        print(f"\n### 按势力分布\n")
        for p, count in sorted(powers.items(), key=lambda x: -x[1]):
            print(f"- {p}: {count}人")




def cmd_timeline(name):
    """显示人物的生平时间线（按卷排序的所有出场记录）"""
    graph_file = GRAPH_DIR / "entities.json"
    entity_info = None
    if graph_file.exists():
        entities = json.loads(graph_file.read_text(encoding="utf-8"))
        for e in entities:
            if e["name"] == name or name in e.get("alias", []):
                entity_info = e
                name = e["name"]
                break

    conn = get_db()
    c = conn.cursor()

    # 搜索所有出场
    search_terms = [name]
    if entity_info:
        search_terms += entity_info.get("alias", [])

    rows = []
    seen_seg_ids = set()
    for term in search_terms:
        c.execute("""SELECT c.id as ch_id, c.title, s.seq, s.time_original,
                            s.time_translated, sen.original, sen.translated
                     FROM sentences sen
                     JOIN segments s ON sen.segment_id = s.id
                     JOIN chapters c ON s.chapter_id = c.id
                     WHERE sen.original LIKE ? OR sen.translated LIKE ?
                     ORDER BY c.id, s.seq""",
                  (f"%{term}%", f"%{term}%"))
        for row in c.fetchall():
            key = (row["ch_id"], row["seq"])
            if key not in seen_seg_ids:
                seen_seg_ids.add(key)
                rows.append(row)

    if entity_info:
        print(f"## {entity_info['name']}")
        print(f"{entity_info.get('llm_introduction', '')}")
        fa = entity_info.get("first_appear")
        la = entity_info.get("last_appear")
        if fa:
            fa_label = f"前{abs(int(fa))}" if int(fa) < 0 else f"公元{fa}"
            la_label = f"前{abs(int(la))}" if la and int(la) < 0 else f"公元{la}" if la else ""
            span = f"{fa_label} ~ {la_label}" if la else fa_label
            print(f"活跃期: {span}")
        print(f"出场次数: {entity_info.get('mention_count', len(rows))}")
        print(f"势力: {entity_info.get('power', '未知')}")
        print()

    if not rows:
        print(f"未找到 '{name}' 的相关记录")
        conn.close()
        return

    # 按卷分组
    current_ch = None
    shown = 0
    max_shown = 20
    for row in rows:
        if shown >= max_shown and len(rows) > max_shown:
            break
        ch_id = row["ch_id"]
        if ch_id != current_ch:
            current_ch = ch_id
            print(f"\n### [{row['title']}]")
        time_str = row["time_original"] or row["time_translated"] or "?"
        text = (row["translated"] or row["original"] or "")[:200]
        # 高亮匹配词
        for term in search_terms[:3]:
            text = text.replace(term, f"**{term}**")
        print(f"> {time_str}: {text}")
        shown += 1

    conn.close()
    if len(rows) > max_shown:
        print(f"\n共 {len(rows)} 条记录（仅显示前 {shown} 条，可缩小检索范围）")
    else:
        print(f"\n共 {len(rows)} 条记录")


def cmd_contemporaries(name):
    """查询与某人同时代活跃的其他人物"""
    graph_file = GRAPH_DIR / "entities.json"
    if not graph_file.exists():
        print("知识图谱尚未构建")
        return

    entities = json.loads(graph_file.read_text(encoding="utf-8"))
    entity_map = {e["name"]: e for e in entities}

    target = entity_map.get(name)
    if not target:
        for e in entities:
            if name in e.get("alias", []):
                target = e
                name = e["name"]
                break

    if not target:
        print(f"未找到人物: {name}")
        return

    target_year = target.get("first_appear")
    if not target_year:
        print(f"{name} 缺少活跃年份信息")
        return

    try:
        ty = int(target_year)
    except (ValueError, TypeError):
        print(f"{name} 活跃年份无效")
        return

    # 同期人物：first_appear 在 target 活跃期前后30年内
    window_start = ty - 40
    window_end = ty + 60

    contemporaries = []
    for e in entities:
        if e["name"] == name:
            continue
        fa = e.get("first_appear")
        if not fa:
            continue
        try:
            fa_int = int(fa)
        except (ValueError, TypeError):
            continue
        if window_start <= fa_int <= window_end:
            contemporaries.append(e)

    contemporaries.sort(key=lambda x: -x.get("mention_count", 0))

    print(f"## {name} 的同时代人物")
    ty_label = f"前{abs(ty)}" if ty < 0 else f"公元{ty}"
    ws_label = f"前{abs(window_start)}" if window_start < 0 else f"公元{window_start}"
    we_label = f"前{abs(window_end)}" if window_end < 0 else f"公元{window_end}"
    print(f"{target.get('llm_introduction', '')}")
    print(f"活跃锚点: {ty_label} | 窗口: {ws_label} ~ {we_label}")
    print(f"同期人物: {len(contemporaries)} 人\n")

    for e in contemporaries:
        fa = e.get("first_appear", "?")
        fa_label = f"前{abs(int(fa))}" if fa != "?" and int(fa) < 0 else f"公元{fa}" if fa != "?" else "?"
        print(f"- **{e['name']}** ({e.get('power','?')}): {e.get('llm_introduction','')} [{fa_label}] ({e.get('mention_count',0)}次)")


def cmd_event(name=None):
    """查询关键事件详情"""
    events_file = ROOT / "data" / "key_events.json"
    if not events_file.exists():
        print("key_events.json 不存在")
        return

    events = json.loads(events_file.read_text(encoding="utf-8"))
    entities_file = GRAPH_DIR / "entities.json"
    entity_map = {}
    if entities_file.exists():
        entity_list = json.loads(entities_file.read_text(encoding="utf-8"))
        entity_map = {e["name"]: e for e in entity_list}

    if name:
        matches = [e for e in events if name in e.get("name", "")]
        if not matches:
            print(f"未找到事件: {name}")
            print(f"可用事件关键词: 安史之乱、玄武门之变、贞观之治、甘露之变...")
            return
        for ev in matches:
            print(f"## {ev['name']}")
            time_label = f"前{abs(ev['time'])}" if ev['time'] < 0 else f"公元{ev['time']}"
            print(f"时间: {time_label}")
            print(f"类型: {ev.get('category', '?')}")
            print(f"地点: {ev.get('location', '不详')}")
            print(f"描述: {ev.get('description', '')}")
            participants = ev.get("participants", [])
            if participants:
                print(f"参与者: {'、'.join(participants)}")
            print()
    else:
        # 列出所有事件
        by_cat = defaultdict(list)
        for ev in events:
            by_cat[ev.get("category", "其他")].append(ev)
        print(f"## 关键事件列表 (共{len(events)}条)\n")
        for cat in ["政变", "军事", "政治", "制度", "文化", "外交", "其他"]:
            if cat in by_cat:
                print(f"\n### {cat} ({len(by_cat[cat])}条)")
                for ev in sorted(by_cat[cat], key=lambda x: x.get("time", 0)):
                    time_label = f"前{abs(ev['time'])}" if ev['time'] < 0 else f"公元{ev['time']}"
                    print(f"- **{time_label}** {ev['name']}")



COMMAND_USAGE = {
    "info": "python zztj.py info",
    "search": "python zztj.py search <关键词>",
    "person": "python zztj.py person <人名>",
    "timeline": "python zztj.py timeline <人名>",
    "contemporaries": "python zztj.py contemporaries <人名>",
    "year": "python zztj.py year <年份>（公元前用负数，如 -403）",
    "range": "python zztj.py range <起始年> <结束年>",
    "chapter": "python zztj.py chapter <卷号1-294>",
    "dynasty": "python zztj.py dynasty <朝代名>",
    "event": "python zztj.py event [事件名]",
    "graph": "python zztj.py graph [实体名]",
}

HELP = """资治通鉴 CLI 查询工具

用法: python zztj.py <command> [args]  (子命令加 -h/--help 查看用法)

命令:
  info                    数据概览
  search <keyword>        全文搜索（文言+白话）
  person <name>           人物出场记录
  timeline <name>         人物生平时间线（按卷排序）
  contemporaries <name>   同时代人物查询
  year <year>             某年事件（公元前用负数，如 -403）
  range <start> <end>     时间段事件
  chapter <n>             阅读某卷全文
  dynasty <name>          朝代概览（周/秦/汉/魏/晋/宋/齐/梁/陈/隋/唐/五代）
  event [name]            关键事件查询（无参数=列表，带参数=详情）
  graph [name]            查看知识图谱（无参数=概览，带参数=查某实体）

示例:
  python zztj.py search "三家分晋"
  python zztj.py timeline "李世民"
  python zztj.py contemporaries "曹操"
  python zztj.py event "玄武门之变"
  python zztj.py year -403
  python zztj.py dynasty 唐
  python zztj.py graph "刘邦"
"""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(HELP)
        sys.exit(0)

    cmd = sys.argv[1]

    # 子命令针对性帮助：`zztj.py <cmd> -h/--help`
    if len(sys.argv) > 2 and sys.argv[2] in ("-h", "--help"):
        usage = COMMAND_USAGE.get(cmd)
        if usage:
            print(usage)
        else:
            print(HELP)
        sys.exit(0)

    try:
        if cmd == "info":
            cmd_info()
        elif cmd == "search":
            keyword = sys.argv[2] if len(sys.argv) > 2 else ""
            if not keyword:
                print("用法: python zztj.py search <关键词>")
            else:
                cmd_search(keyword)
        elif cmd == "person":
            name = sys.argv[2] if len(sys.argv) > 2 else ""
            if not name:
                print("用法: python zztj.py person <人名>")
            else:
                cmd_person(name)
        elif cmd == "timeline":
            name = sys.argv[2] if len(sys.argv) > 2 else ""
            if not name:
                print("用法: python zztj.py timeline <人名>")
            else:
                cmd_timeline(name)
        elif cmd == "contemporaries":
            name = sys.argv[2] if len(sys.argv) > 2 else ""
            if not name:
                print("用法: python zztj.py contemporaries <人名>")
            else:
                cmd_contemporaries(name)
        elif cmd == "event":
            name = sys.argv[2] if len(sys.argv) > 2 else None
            cmd_event(name)
        elif cmd == "year":
            year = int(sys.argv[2]) if len(sys.argv) > 2 else 0
            cmd_year(year)
        elif cmd == "range":
            if len(sys.argv) < 4:
                print("用法: python zztj.py range <起始年> <结束年>")
            else:
                cmd_range(int(sys.argv[2]), int(sys.argv[3]))
        elif cmd == "chapter":
            ch = int(sys.argv[2]) if len(sys.argv) > 2 else 0
            if ch < 1 or ch > 294:
                print(f"卷号需在1-294之间")
            else:
                cmd_chapter(ch)
        elif cmd == "dynasty":
            name = sys.argv[2] if len(sys.argv) > 2 else ""
            if not name:
                print(f"可用朝代: {', '.join(DYNASTY_MAP.keys())}")
            else:
                cmd_dynasty(name)
        elif cmd == "graph":
            q = sys.argv[2] if len(sys.argv) > 2 else None
            cmd_graph(q)
        elif cmd in ("-h", "--help", "help"):
            print(HELP)
        else:
            print(f"未知命令: {cmd}")
            print(HELP)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        print("用法: python zztj.py help  查看全部命令", file=sys.stderr)
        sys.exit(1)
