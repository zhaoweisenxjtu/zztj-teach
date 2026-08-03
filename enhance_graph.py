#!/usr/bin/env python3
"""
图谱增强模块：关系类型化 + 势力演变 + 事件因果链
在 build_graph.py 之后运行，对已有 entities.json 和 relations.json 进行后处理
"""
import json
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).parent
GRAPH_DIR = ROOT / "graph"
DATA_DIR = ROOT / "data"
INDEX_DIR = ROOT / "index"

# 势力敌对关系定义（手工标注，基于历史知识；已去重）
HOSTILE_POWERS = [
    ({"西汉", "西楚"}, "楚汉战争"),
    ({"西汉", "匈奴"}, "汉匈战争"),
    ({"曹魏", "蜀汉"}, "三国对立"),
    ({"曹魏", "东吴"}, "三国对立"),
    ({"蜀汉", "东吴"}, "三国对立(后期)"),
    ({"东晋", "前秦"}, "淝水之战"),
    ({"东晋", "汉赵"}, "五胡乱华"),
    ({"东晋", "后赵"}, "五胡乱华"),
    ({"东晋", "北魏"}, "南北朝"),
    ({"北魏", "刘宋"}, "南北朝对峙"),
    ({"北魏", "萧齐"}, "南北朝对峙"),
    ({"北魏", "南梁"}, "南北朝对峙"),
    ({"东魏", "西魏"}, "东西魏对峙"),
    ({"北齐", "北周"}, "周齐对峙"),
    ({"唐朝", "燕国"}, "安史之乱"),
    ({"唐朝", "大齐"}, "黄巢起义"),
    ({"隋朝", "瓦岗军"}, "隋末起义"),
    ({"隋朝", "夏国"}, "隋末起义"),
    ({"隋朝", "郑国"}, "隋末起义"),
    ({"唐朝", "吐蕃"}, "唐蕃战争"),
    ({"唐朝", "南诏"}, "唐诏战争"),
    ({"后梁", "后唐"}, "后唐灭梁"),
    ({"后唐", "前蜀"}, "后唐灭前蜀"),
    ({"后晋", "契丹"}, "契丹灭晋"),
    ({"后汉", "契丹"}, "契丹交锋"),
    ({"后周", "北汉"}, "高平之战"),
    ({"后周", "南唐"}, "周世宗南征"),
    ({"南唐", "吴国"}, "南唐灭吴"),
    ({"南唐", "吴越"}, "南唐吴越争战"),
    ({"南唐", "北宋"}, "宋灭南唐"),
    ({"后蜀", "北宋"}, "北宋平蜀"),
    ({"南汉", "北宋"}, "北宋平南汉"),
    ({"南汉", "南唐"}, "南汉南唐相争"),
    ({"北宋", "契丹"}, "宋辽对峙"),
    ({"北汉", "北宋"}, "宋平北汉"),
    ({"前秦", "东晋"}, "淝水之战"),
]

# 继承关系：同一朝代皇帝按时间排序
IMPERIAL_POWERS = ["西汉", "东汉", "曹魏", "蜀汉", "东吴", "西晋", "东晋",
                   "刘宋", "南齐", "南梁", "南陈", "北魏", "东魏", "西魏",
                   "北齐", "北周", "隋朝", "唐朝",
                   "后梁", "后唐", "后晋", "后汉", "后周", "北宋",
                   "前燕", "后燕", "南燕", "前秦", "后秦", "前赵", "后赵",
                   "前蜀", "后蜀", "南唐", "南汉", "吴越", "周朝"]


def load_data():
    entities = json.loads((GRAPH_DIR / "entities.json").read_text(encoding="utf-8"))
    relations = json.loads((GRAPH_DIR / "relations.json").read_text(encoding="utf-8"))
    events = json.loads((DATA_DIR / "key_events.json").read_text(encoding="utf-8"))
    return entities, relations, events


def is_emperor(e):
    """判断是否为皇帝/君主

    判定依据（按可信度排序）：
    1. intro 中直接出现君主身份关键词
    2. 姓名含庙号/帝号后缀（X帝 / X祖 / X宗），资治通鉴中基本对应君主
    """
    import re
    intro = e.get("llm_introduction", "")
    name = e["name"]
    emperor_keywords = ["皇帝", "开国", "国君", "君主", "单于", "大汗",
                        "建立者", "奠基者", "汉高祖", "临朝称制",
                        "唐太宗", "汉武帝", "称帝", "女皇帝",
                        "即位", "帝王", "禅让", "天子", "国主", "僭号"]
    if any(kw in intro for kw in emperor_keywords):
        return True
    # 庙号/帝号后缀：X帝、X祖、X宗 结尾
    if re.search(r"(.+)(帝|太祖|太宗|高宗|中宗|世宗|显宗|肃宗|代宗|德宗|宪宗|穆宗|敬宗|文宗|武宗|宣宗|懿宗|僖宗|昭宗|哀宗)$", name):
        return True
    return False


def is_minister(e):
    """判断是否为大臣/将领

    基于 intro 中的官职称谓关键词匹配，扩充常见官职以降低漏判。
    """
    intro = e.get("llm_introduction", "")
    minister_keywords = ["丞相", "宰相", "名将", "谋士", "大将", "将军",
                        "太尉", "司徒", "司空", "大司马", "中书令",
                        "尚书", "御史", "太守", "刺史", "节度使",
                        "宦官", "酷吏", "军阀",
                        "相国", "廷尉", "光禄大夫", "太傅", "太保", "太师",
                        "骠骑将军", "车骑将军", "都护", "都督", "总督",
                        "元帅", "军师", "参军", "从事", "司马", "长史",
                        "国相", "郎将", "校尉", "都尉", "县令", "郡守"]
    return any(kw in intro for kw in minister_keywords)


def classify_relations(entities, relations):
    """为关系添加类型标记"""
    entity_map = {e["name"]: e for e in entities}
    power_map = defaultdict(set)  # power -> {entity names}
    for e in entities:
        p = e.get("power", "未知")
        # 拆分复合势力
        for part in p.split("/"):
            power_map[part.strip()].add(e["name"])

    # 标记皇帝和大臣
    emperors = {e["name"] for e in entities if is_emperor(e)}
    ministers = {e["name"] for e in entities if is_minister(e)}

    enhanced = []
    type_stats = Counter()

    for r in relations:
        r_type = r.get("action", "共现")

        if r_type == "参与事件":
            r = dict(r)
            r["relation_type"] = "event"
            type_stats["事件"] += 1
            enhanced.append(r)
            continue

        # 共现关系 → 分类
        from_names = r.get("from", [])
        to_names = r.get("to", [])
        if not from_names or not to_names:
            type_stats["其他"] += 1
            enhanced.append(r)
            continue

        a = from_names[0]
        b = to_names[0]
        ea = entity_map.get(a, {})
        eb = entity_map.get(b, {})

        power_a = ea.get("power", "")
        power_b = eb.get("power", "")
        is_a_emperor = a in emperors
        is_b_emperor = b in emperors
        is_a_minister = a in ministers
        is_b_minister = b in ministers

        # 分类逻辑
        classified = False

        # 1. 继承关系：同一power的皇帝
        if power_a == power_b and is_a_emperor and is_b_emperor:
            r = dict(r)
            r["action"] = "继承"
            r["relation_type"] = "succession"
            type_stats["继承"] += 1
            enhanced.append(r)
            classified = True

        # 2. 同僚关系：同一power的两个大臣
        elif power_a == power_b and is_a_minister and is_b_minister:
            r = dict(r)
            r["action"] = "同僚"
            r["relation_type"] = "colleague"
            type_stats["同僚"] += 1
            enhanced.append(r)
            classified = True

        # 3. 君臣关系：同一power的君主与大臣
        elif power_a == power_b:
            if is_a_emperor and is_b_minister:
                r = dict(r)
                r["action"] = "君臣"
                r["relation_type"] = "lord_vassal"
                type_stats["君臣"] += 1
                enhanced.append(r)
                classified = True
            elif is_b_emperor and is_a_minister:
                r = dict(r)
                r["action"] = "君臣"
                r["relation_type"] = "lord_vassal"
                type_stats["君臣"] += 1
                enhanced.append(r)
                classified = True

        # 4. 敌对关系
        if not classified:
            for hostile_set, _ in HOSTILE_POWERS:
                pa_clean = set(power_a.split("/"))
                pb_clean = set(power_b.split("/"))
                if (pa_clean & hostile_set) and (pb_clean & hostile_set) and pa_clean != pb_clean:
                    r = dict(r)
                    r["action"] = "敌对"
                    r["relation_type"] = "opposition"
                    type_stats["敌对"] += 1
                    enhanced.append(r)
                    classified = True
                    break

        # 5. 同势力（未进一步分类）
        if not classified and power_a == power_b:
            r = dict(r)
            r["action"] = "同势力"
            r["relation_type"] = "same_power"
            type_stats["同势力"] += 1
            enhanced.append(r)
            classified = True

        # 6. 默认共现
        if not classified:
            r = dict(r)
            r["relation_type"] = "co_occurrence"
            type_stats["共现"] += 1
            enhanced.append(r)

    print("关系类型分布:")
    for t, c in type_stats.most_common():
        print(f"  {t}: {c}")

    return enhanced


def build_force_evolution(entities):
    """构建势力演变时间线"""
    from collections import defaultdict
    entity_map = {e["name"]: e for e in entities}

    # 按势力分组
    by_power = defaultdict(list)
    for e in entities:
        p = e.get("power", "未知")
        for part in p.split("/"):
            by_power[part.strip()].append(e)

    # 每个势力的活跃时间范围
    evolution = []
    for power, members in by_power.items():
        years = []
        for m in members:
            fa = m.get("first_appear")
            la = m.get("last_appear")
            if fa:
                try:
                    years.append(int(fa))
                except:
                    pass
        if years:
            years.sort()
            evolution.append({
                "power": power,
                "entity_count": len(members),
                "earliest_mention": min(years),
                "latest_mention": max(years),
                "timespan": max(years) - min(years) if len(years) > 1 else 0,
                "key_figures": [m["name"] for m in sorted(members, key=lambda x: -x.get("mention_count", 0))[:5]],
            })

    evolution.sort(key=lambda x: x["earliest_mention"])

    # 保存
    (GRAPH_DIR / "force_evolution.json").write_text(
        json.dumps(evolution, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成 Markdown 索引
    lines = ["# 势力演变时间线\n",
             f"覆盖 {len(evolution)} 个势力/政权\n"]
    for ev in evolution:
        era_start = f"前{abs(ev['earliest_mention'])}" if ev['earliest_mention'] < 0 else f"公元{ev['earliest_mention']}"
        era_end = f"前{abs(ev['latest_mention'])}" if ev['latest_mention'] < 0 else f"公元{ev['latest_mention']}"
        lines.append(f"\n## {ev['power']} ({ev['entity_count']}人)")
        lines.append(f"活跃期: {era_start} ~ {era_end} (跨度{ev['timespan']}年)")
        lines.append(f"代表人物: {'、'.join(ev['key_figures'][:5])}")

    (INDEX_DIR / "force_evolution.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"势力演变时间线: {len(evolution)} 个势力")
    return evolution


def build_event_chains(events, entities, relations):
    """构建事件因果关系链"""
    entity_names = {e["name"] for e in entities}

    # 按时间排序事件
    sorted_events = sorted(events, key=lambda x: x.get("time", 9999))

    # 构建事件因果关系（时间相近 + 相同类别/参与者）
    chains = []
    for i, e1 in enumerate(sorted_events):
        for j in range(i + 1, min(i + 6, len(sorted_events))):  # 最多往后看5个
            e2 = sorted_events[j]
            t1, t2 = e1["time"], e2["time"]
            if t1 is None or t2 is None:
                continue
            gap = t2 - t1
            if gap > 50:  # 50年内
                break

            # 共享参与者
            p1 = set(e1.get("participants", [])) & entity_names
            p2 = set(e2.get("participants", [])) & entity_names
            shared = p1 & p2

            # 相同类别
            same_cat = e1.get("category") == e2.get("category")

            if (shared or same_cat) and gap <= 20:
                chains.append({
                    "cause": e1["name"],
                    "effect": e2["name"],
                    "cause_time": t1,
                    "effect_time": t2,
                    "gap_years": gap,
                    "shared_participants": list(shared),
                    "same_category": same_cat,
                })

    # 去重并排序
    chains.sort(key=lambda x: (x["cause_time"], x["gap_years"]))
    seen = set()
    unique_chains = []
    for c in chains:
        key = (c["cause"], c["effect"])
        if key not in seen:
            seen.add(key)
            unique_chains.append(c)

    (GRAPH_DIR / "event_chains.json").write_text(
        json.dumps(unique_chains, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成 Markdown 索引
    lines = ["# 事件因果链\n", f"共 {len(unique_chains)} 条因果关系\n"]
    for c in unique_chains[:100]:
        cause_time_label = f"前{abs(c['cause_time'])}" if c['cause_time'] < 0 else f"公元{c['cause_time']}"
        effect_time_label = f"前{abs(c['effect_time'])}" if c['effect_time'] < 0 else f"公元{c['effect_time']}"
        lines.append(f"- **{cause_time_label}** {c['cause']} → **{effect_time_label}** {c['effect']} (间隔{c['gap_years']}年)")

    (INDEX_DIR / "event_chains.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"事件因果链: {len(unique_chains)} 条")
    return unique_chains


def main():
    print("=== 图谱增强 ===\n")

    entities, relations, events = load_data()
    print(f"输入: {len(entities)} 实体, {len(relations)} 关系, {len(events)} 事件")

    # 1. 关系类型化
    print("\n--- 1. 关系类型化 ---")
    enhanced_relations = classify_relations(entities, relations)
    (GRAPH_DIR / "relations.json").write_text(
        json.dumps(enhanced_relations, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已保存 {len(enhanced_relations)} 条关系")

    # 2. 势力演变
    print("\n--- 2. 势力演变时间线 ---")
    build_force_evolution(entities)

    # 3. 事件因果链
    print("\n--- 3. 事件因果链 ---")
    build_event_chains(events, entities, relations)

    # 4. 更新关系统计（复用公共函数，P1-7）
    from build_graph import write_graph_stats
    write_graph_stats(entities, enhanced_relations, INDEX_DIR)
    print(f"\n=== 图谱增强完成 ===")


if __name__ == "__main__":
    main()
