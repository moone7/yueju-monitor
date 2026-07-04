#!/usr/bin/env python3
"""
generate.py — 读取 shows.json + template.html → 生成 index.html

核心功能：
1. 根据当前日期自动计算每场演出的状态（今日开演/已演/明日开演/售票中）
2. 生成演出卡片 HTML
3. 生成紧急提醒和今日新动态
4. 生成 PERF_DATES 和 STAR_IDS 数据
5. 填充模板占位符，输出 index.html
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# 配置
# ============================================================
STAR_ACTOR = "陆志艳"
WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# ============================================================
# 日期工具
# ============================================================
def get_today():
    """返回今天 00:00 的 datetime"""
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

def date_str(dt):
    """datetime → 'YYYY-MM-DD'"""
    return dt.strftime("%Y-%m-%d")

def format_report_date(dt):
    """→ '2026年7月4日'"""
    return f"{dt.year}年{dt.month}月{dt.day}日"

def format_report_date_badge(dt):
    """→ '2026年7月4日 星期六'"""
    return f"{dt.year}年{dt.month}月{dt.day}日 {WEEKDAYS_CN[dt.weekday()]}"

def format_data_updated():
    """→ '2026-07-04 07:00'"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def format_show_date(date_iso, time_str):
    """→ '7月4日（周六）19:30'"""
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    weekday = WEEKDAYS_CN[dt.weekday()].replace("星期", "周")
    return f"{dt.month}月{dt.day}日（{weekday}）{time_str}"

# ============================================================
# 状态计算
# ============================================================
def compute_card_class(date_iso, today):
    """返回 perf-card 的附加 class"""
    if date_iso < date_str(today):
        return ""                    # 已演
    if date_iso == date_str(today):
        return "today"
    if date_iso == date_str(today + timedelta(days=1)):
        return "tomorrow"
    return ""

def compute_tags(date_iso, today, is_star):
    """返回 (tag_class, tag_text) 列表"""
    tags = []
    if is_star:
        tags.append(("tag-star", "⭐ 陆志艳"))
    
    if date_iso < date_str(today):
        tags.append(("tag-done", "✅ 已演"))
    elif date_iso == date_str(today):
        tags.append(("tag-urgent", "🔥 今日开演"))
        tags.append(("tag-on-sale", "售票中"))
    elif date_iso == date_str(today + timedelta(days=1)):
        tags.append(("tag-urgent", "🔥 明日开演"))
        tags.append(("tag-on-sale", "售票中"))
    else:
        tags.append(("tag-on-sale", "售票中"))
    
    return tags

# ============================================================
# HTML 生成
# ============================================================
def html_escape(text):
    """转义 HTML 特殊字符"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def format_cast_html(cast, is_star=False):
    """格式化主演文本，高亮陆志艳"""
    if is_star and STAR_ACTOR in cast:
        # 将陆志艳用 <strong> 包裹
        cast = cast.replace(STAR_ACTOR, f'<strong style="color:#ffd700;">{STAR_ACTOR}</strong>')
    return cast

def generate_card_html(show, today, is_star_card=False):
    """生成单个演出卡片的 HTML"""
    card_class = compute_card_class(show['date'], today)
    tags = compute_tags(show['date'], today, show['is_star'])
    
    # 卡片 class
    classes = "perf-card"
    if is_star_card:
        classes += " star"
    if card_class:
        classes += f" {card_class}"
    
    # 城市
    city_html = ""
    if show.get('city'):
        city_html = f'\n<span><span class="meta-icon">🏙️</span>{show["city"]}</span>'
    
    # 主演
    cast_html = format_cast_html(show['cast'], show['is_star'])
    
    # 标签
    tags_html = "\n".join(
        f'<span class="tag {tc}">{tt}</span>' for tc, tt in tags
    )
    
    # 票价（支持小字补充）
    price = show.get('price', '以场馆公布为准')
    if ' · ' in price:
        parts = price.split(' · ', 1)
        price_html = parts[0]
        if len(parts) > 1 and parts[1]:
            # 把括号内容放到 <small>
            small_text = parts[1].strip('()')
            if small_text:
                price_html = f'{parts[0]}<br/><small>{small_text}</small>'
    else:
        price_html = price
    
    # margin-top for star cards after first
    style_attr = ' style="margin-top:12px;"' if is_star_card else ''
    
    return f"""<div class="{classes}" data-date="{show['date']}" data-id="{show['id']}" data-time="{show['time']}" data-title="{show['title']}" data-venue="{show['venue']}"{style_attr}>
<div class="perf-info">
<div class="perf-title">{show['title']} <em>{show.get('subtitle', '')}</em></div>
<div class="perf-meta">
<span><span class="meta-icon">📅</span>{format_show_date(show['date'], show['time'])}</span>
<span><span class="meta-icon">📍</span>{show['venue']}</span>{city_html}
</div>
<div class="perf-cast">
<strong>主演：</strong>{cast_html}<br/>
<strong>演出单位：</strong>{show.get('troupe', '')}
        </div>
</div>
<div class="perf-side">
{tags_html}
<button class="buy-btn" onclick="toggleBought(this)"><span class="btn-icon">🎟️</span><span class="btn-text">标记已购</span></button>
<div class="perf-price">{price_html}</div></div>

</div>"""


def generate_star_cards(shows, today):
    """生成陆志艳特别关注区的卡片 HTML"""
    star_shows = [s for s in shows if s['is_star']]
    star_shows.sort(key=lambda s: s['date'])
    
    cards = []
    for i, show in enumerate(star_shows):
        html = generate_card_html(show, today, is_star_card=True)
        # 第一张卡片不需要 margin-top
        if i == 0:
            html = html.replace(' style="margin-top:12px;"', '')
        cards.append(html)
    
    return "\n".join(cards)


def generate_month_cards(shows, today, month):
    """生成指定月份的演出卡片 HTML"""
    month_shows = [s for s in shows if not s['is_star'] and s['date'].startswith(f"2026-{month:02d}")]
    month_shows.sort(key=lambda s: (s['date'], s['time']))
    
    cards = [generate_card_html(show, today) for show in month_shows]
    return "\n".join(cards)


def generate_perf_dates(shows):
    """生成 PERF_DATES JS 对象"""
    dates = {}
    for show in shows:
        d = show['date']
        if d not in dates:
            dates[d] = []
        dates[d].append(show['id'])
    
    lines = []
    for d in sorted(dates.keys()):
        ids = ', '.join(f'"{sid}"' for sid in dates[d])
        lines.append(f'  "{d}": [{ids}],')
    
    return "{\n" + "\n".join(lines) + "\n}"


def generate_star_ids(shows):
    """生成 STAR_IDS JS 数组"""
    star_ids = [s['id'] for s in shows if s['is_star']]
    ids_str = ', '.join(f'"{sid}"' for sid in star_ids)
    return f'[{ids_str}]'


# ============================================================
# 提醒生成
# ============================================================
def clean_title(title):
    """去掉剧目前缀和书名号，返回纯剧名"""
    # 去掉常见前缀
    prefixes = ['大型神话越剧', '小剧场实验越剧', '小剧场越剧', '新编历史故事剧', '越剧']
    cleaned = title
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    # 去掉书名号
    cleaned = cleaned.strip('《》')
    return cleaned.strip()


def format_show_list(shows):
    """格式化演出列表为提醒文本"""
    parts = []
    for s in shows:
        dt = datetime.strptime(s['date'], "%Y-%m-%d")
        title_clean = clean_title(s['title'])
        parts.append(f"{dt.month}月{dt.day}日 {s['venue']}《{title_clean}》")
    return "、".join(parts)


def format_star_list(shows):
    """格式化陆志艳演出列表"""
    parts = []
    for s in shows:
        dt = datetime.strptime(s['date'], "%Y-%m-%d")
        # 提取角色
        role = ""
        role_match = re.search(r'陆志艳[）)）]?[（(]([^）)]+)', s['cast'])
        if role_match:
            role = f"（饰{role_match.group(1)}）"
        elif "陆志艳" in s['cast']:
            # 尝试其他格式
            role_match2 = re.search(r'陆志艳[：:]\s*(\S+)', s['cast'])
            if role_match2:
                role = f"（饰{role_match2.group(1)}）"
        
        title_short = clean_title(s['title'])
        venue_short = s['venue'].replace('上海', '').replace('大剧院', '').replace('·大剧场', '').replace('·小剧场', '').replace('·戏·聚空间', '')
        parts.append(f"{dt.month}月{dt.day}日{venue_short}《{title_short}》{role}")
    return " → ".join(parts)


def generate_alert_urgent(shows, today):
    """生成紧急提醒内容"""
    today_str = date_str(today)
    tomorrow_str = date_str(today + timedelta(days=1))
    
    lines = []
    
    # 今日开演
    today_shows = [s for s in shows if s['date'] == today_str]
    if today_shows:
        lines.append(f"· <strong>今日开演：</strong>{format_show_list(today_shows)}。<br/>")
    
    # 明日开演
    tomorrow_shows = [s for s in shows if s['date'] == tomorrow_str]
    if tomorrow_shows:
        lines.append(f"· <strong>明日开演：</strong>{format_show_list(tomorrow_shows)}。<br/>")
    
    # 陆志艳近期
    star_shows = [s for s in shows if s['is_star'] and s['date'] >= today_str]
    if star_shows:
        lines.append(f"· <strong>⭐ 陆志艳近期：</strong>{format_star_list(star_shows)}。<br/>")
    
    # 近期开票提醒（未来7天内）
    week_ahead = date_str(today + timedelta(days=7))
    upcoming = [s for s in shows if today_str < s['date'] <= week_ahead and not s['is_star']]
    if upcoming:
        venue_set = set()
        for s in upcoming:
            venue_set.add(s['venue'])
        venues_text = "、".join(list(venue_set)[:3])
        lines.append(f"· <strong>一周内演出：</strong>{format_show_list(upcoming[:4])}{'等' if len(upcoming) > 4 else ''}。<br/>")
    
    if not lines:
        lines.append("· 暂无近期高优提醒。<br/>")
    
    return "\n      ".join(lines)


def generate_alert_new(shows, today):
    """生成今日新动态内容"""
    today_str = date_str(today)
    yesterday_str = date_str(today - timedelta(days=1))
    
    lines = []
    
    # 今日开演
    today_shows = [s for s in shows if s['date'] == today_str]
    if today_shows:
        cities = set(s['city'] for s in today_shows if s.get('city'))
        if len(cities) > 1:
            lines.append(f"· <strong>今日多城联动：</strong>{format_show_list(today_shows)}。<br/>")
        else:
            lines.append(f"· <strong>今日开演：</strong>{format_show_list(today_shows)}。<br/>")
    
    # 昨日回顾
    yesterday_shows = [s for s in shows if s['date'] == yesterday_str]
    if yesterday_shows:
        lines.append(f"· <strong>昨日回顾：</strong>{format_show_list(yesterday_shows)} 已圆满演出。<br/>")
    
    # 陆志艳近期
    star_upcoming = [s for s in shows if s['is_star'] and s['date'] >= today_str]
    if star_upcoming:
        lines.append(f"· <strong>⭐ 陆志艳行程：</strong>共 {len(star_upcoming)} 场 — {format_star_list(star_upcoming)}。<br/>")
    
    # 京津冀巡演
    aug_shows = [s for s in shows if s['date'].startswith('2026-08') and '北京' in s.get('city', '') + s.get('venue', '')]
    aug_shows += [s for s in shows if s['date'].startswith('2026-08') and '天津' in s.get('city', '') + s.get('venue', '')]
    aug_shows += [s for s in shows if s['date'].startswith('2026-08') and '廊坊' in s.get('city', '') + s.get('venue', '')]
    aug_shows += [s for s in shows if s['date'].startswith('2026-09') and '北京' in s.get('city', '') + s.get('venue', '')]
    if aug_shows:
        cities_count = len(set(s.get('city', '') for s in aug_shows))
        lines.append(f"· <strong>京津冀巡演进行中：</strong>8-9月共 {len(aug_shows)} 场（北大/吉祥大戏院/国家大剧院/天津中国大戏院/廊坊壹佰剧院/北京艺术中心）。<br/>")
    
    # 宛平剧院
    wanping = [s for s in shows if '宛平' in s.get('venue', '') and s['date'] >= today_str]
    if wanping:
        lines.append(f"· <strong>宛平剧院近期：</strong>{format_show_list(wanping[:3])}{'等' if len(wanping) > 3 else ''}。<br/>")
    
    if not lines:
        lines.append("· 今日暂无新动态。<br/>")
    
    return "\n      ".join(lines)


# ============================================================
# 主函数
# ============================================================
def main():
    # 读取数据
    data = json.loads(Path("shows.json").read_text(encoding="utf-8"))
    shows = data['shows']
    
    today = get_today()
    
    # 计算统计
    total = len(shows)
    star_count = len([s for s in shows if s['is_star']])
    cities = set(s['city'] for s in shows if s.get('city'))
    
    # 生成内容
    report_date = format_report_date(today)
    report_date_badge = format_report_date_badge(today)
    data_updated = format_data_updated()
    
    star_cards = generate_star_cards(shows, today)
    july_cards = generate_month_cards(shows, today, 7)
    aug_cards = generate_month_cards(shows, today, 8)
    sep_cards = generate_month_cards(shows, today, 9)
    
    perf_dates_json = generate_perf_dates(shows)
    star_ids_json = generate_star_ids(shows)
    
    alert_urgent = generate_alert_urgent(shows, today)
    alert_new = generate_alert_new(shows, today)
    
    # 读取模板并替换
    template = Path("template.html").read_text(encoding="utf-8")
    
    replacements = {
        "{{REPORT_DATE}}": report_date,
        "{{REPORT_DATE_BADGE}}": report_date_badge,
        "{{DATA_UPDATED}}": data_updated,
        "{{STAT_TOTAL}}": str(total),
        "{{STAT_STAR}}": str(star_count),
        "{{STAT_CITIES}}": str(len(cities)),
        "{{STAR_CARDS}}": star_cards,
        "{{PERF_CARDS_JULY}}": july_cards,
        "{{PERF_CARDS_AUG}}": aug_cards,
        "{{PERF_CARDS_SEP}}": sep_cards,
        "{{PERF_DATES_JSON}}": perf_dates_json,
        "{{STAR_IDS_JSON}}": star_ids_json,
        "{{ALERT_URGENT}}": alert_urgent,
        "{{ALERT_NEW}}": alert_new,
    }
    
    html = template
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    
    # 验证无残留占位符
    remaining = re.findall(r'\{\{\w+\}\}', html)
    if remaining:
        print(f"⚠️ 警告：{len(remaining)} 个占位符未替换：{set(remaining)}")
    
    # ============================================================
    # FINGERPRINT 稳定性检查
    # 确保 date+title+venue 与上次生成一致，保护已购状态
    # ============================================================
    fingerprint_file = Path(".fingerprint_cache")
    current_fps = {}
    for s in shows:
        raw = f"{s['date']}|{s['title']}|{s['venue']}"
        current_fps[s['id']] = raw
    
    if fingerprint_file.exists():
        try:
            old_fps = json.loads(fingerprint_file.read_text(encoding="utf-8"))
            changed = []
            for sid, raw in current_fps.items():
                if sid in old_fps and old_fps[sid] != raw:
                    changed.append(f"  ⚠️ {sid}: \"{old_fps[sid]}\" → \"{raw}\"")
            if changed:
                print(f"\n🚨 警告：{len(changed)} 场演出的 fingerprint 输入值发生变化！")
                print("   已购状态可能丢失！请检查 shows.json 是否修改了 date/title/venue。")
                for c in changed:
                    print(c)
        except:
            pass
    
    fingerprint_file.write_text(json.dumps(current_fps, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 写入
    Path("index.html").write_text(html, encoding="utf-8")
    print(f"✅ index.html 生成完成")
    print(f"   报告日期：{report_date}（{WEEKDAYS_CN[today.weekday()]}）")
    print(f"   演出场次：{total}（陆志艳 {star_count} 场）")
    print(f"   涉及城市：{len(cities)} 个")
    print(f"   数据时间：{data_updated}")


if __name__ == "__main__":
    main()
