#!/usr/bin/env python3
"""
generate.py — 读取 shows.json + template.html → 生成 index.html

核心功能：
1. 根据当前日期自动计算每场演出的状态（今日开演/已演/明日开演/售票中）
2. 生成演出卡片 HTML
3. 智能提醒生成（基于历史对比，发现新增/变化）
4. 生成 PERF_DATES 和 STAR_IDS 数据
5. 填充模板占位符，输出 index.html

历史对比：读取 shows_history/latest.json，对比找出新增演出
"""
import json
import re
import html
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# 配置
# ============================================================
STAR_ACTOR = "陆志艳"
WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# ============================================================
# 历史对比
# ============================================================
def load_previous_shows():
    """读取上次的历史数据（用于对比发现新增演出）"""
    latest_file = Path("shows_history/latest.json")
    if not latest_file.exists():
        return []
    
    try:
        return json.loads(latest_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️ 读取历史数据失败: {e}")
        return []

def find_new_shows(current_shows, previous_shows):
    """找出新增的演出（对比 date+title+venue）"""
    if not previous_shows:
        return []
    
    # 建立上次演出的索引
    prev_keys = set()
    for show in previous_shows:
        key = f"{show['date']}|{show['title']}|{show['venue']}"
        prev_keys.add(key)
    
    # 找出新增的
    new_shows = []
    for show in current_shows:
        key = f"{show['date']}|{show['title']}|{show['venue']}"
        if key not in prev_keys:
            new_shows.append(show)
    
    return new_shows

def find_cancelled_shows(current_shows, previous_shows):
    """找出"本次新官宣取消"的演出：上次在售/未标取消，本次 cancelled=True"""
    if not previous_shows:
        return []
    prev_state = {}
    for show in previous_shows:
        key = f"{show['date']}|{show['title']}|{show['venue']}"
        prev_state[key] = show.get('cancelled', False)
    cancelled_new = []
    for show in current_shows:
        if not show.get('cancelled'):
            continue
        key = f"{show['date']}|{show['title']}|{show['venue']}"
        prev_cancel = prev_state.get(key, None)
        if prev_cancel is not True:  # 上次未标取消（或根本没有这场）→ 本次才标取消
            cancelled_new.append(show)
    return cancelled_new

def clean_title(title):
    """去掉剧目前缀和书名号，返回纯剧目名"""
    prefixes = ['大型神话越剧', '小剧场实验越剧', '小剧场越剧', '新编历史故事剧', '越剧']
    cleaned = title
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    cleaned = cleaned.strip('《》')
    return cleaned.strip()

# 非售票活动类型 → 配色（青/蓝/粉/金）
EVENT_TYPE_STYLE = {
    '访谈':   {'bg': 'rgba(110,207,198,0.88)', 'fg': '#06201e', 'dot': '#6ecfc6'},
    '讲座':   {'bg': 'rgba(140,170,230,0.88)', 'fg': '#0a1530', 'dot': '#8caaeb'},
    '见面会': {'bg': 'rgba(230,160,200,0.88)', 'fg': '#2a0a20', 'dot': '#e6a0c8'},
    '活动':   {'bg': 'rgba(201,169,110,0.88)', 'fg': '#0d0c0a', 'dot': '#c9a96e'},
}

def is_event(show):
    """判断是否为非售票活动（访谈 / 讲座 / 见面会）"""
    et = show.get('event_type', '')
    return bool(et) and et != '演出'


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

def esc(text):
    """转义任意动态文本（含引号）用于 HTML 文本与属性上下文，防 XSS 注入。

    quote=True 同时转义 ' 与 "，使 data-* 属性值即便含引号也不会提前截断属性、
    造成属性逃逸。所有来自 shows.json / events.json（抓取或人工录入）的字段都必须经此处理。
    """
    return html.escape(str(text), quote=True)

def format_cast_html(cast, is_star=False):
    """格式化主演文本，高亮陆志艳（先转义，再注入高亮标签，防 XSS）"""
    cast_esc = esc(cast)
    if is_star and STAR_ACTOR in cast:
        cast_esc = cast_esc.replace(esc(STAR_ACTOR), f'<strong style="color:#ffd700;">{STAR_ACTOR}</strong>')
    return cast_esc

def generate_card_html(show, today, is_star_card=False):
    """生成单个演出卡片的 HTML（所有动态字段均 HTML 转义，防 XSS）"""
    cancelled = show.get('cancelled', False)
    if cancelled:
        classes = "perf-card cancelled"
        if is_star_card:
            classes += " star"
        tags = [("tag-cancelled", "⚠️ 官宣取消")]
    else:
        card_class = compute_card_class(show['date'], today)
        tags = compute_tags(show['date'], today, show['is_star'])
        classes = "perf-card"
        if is_star_card:
            classes += " star"
        if card_class:
            classes += f" {card_class}"

    # 城市
    city_html = ""
    if show.get('city'):
        city_html = f'\n<span><span class="meta-icon">🏙️</span>{esc(show["city"])}</span>'

    # 主演（含陆志艳高亮，已内部转义）
    cast_html = format_cast_html(show['cast'], show['is_star'])

    # 标签（tc=类名，tt=显示文本，均转义）
    tags_html = "\n".join(
        f'<span class="tag {esc(tc)}">{esc(tt)}</span>' for tc, tt in tags
    )

    # 票价（支持小字补充），文本部分必须转义
    price = show.get('price', '以场馆公布为准')
    if ' · ' in price:
        parts = price.split(' · ', 1)
        small_text = parts[1].strip('()')
        if small_text:
            price_html = f'{esc(parts[0])}<br/><small>{esc(small_text)}</small>'
        else:
            price_html = esc(parts[0])
    else:
        price_html = esc(price)

    # margin-top for star cards after first
    style_attr = ' style="margin-top:12px;"' if is_star_card else ''
    cancelled_attr = ' data-cancelled="1"' if cancelled else ''
    buy_btn_html = '' if cancelled else '<button class="buy-btn" onclick="toggleBought(this)"><span class="btn-icon">🎟️</span><span class="btn-text">标记已购</span></button>'

    return f"""<div class="{classes}" data-date="{esc(show['date'])}" data-id="{esc(show['id'])}" data-time="{esc(show['time'])}" data-title="{esc(show['title'])}" data-venue="{esc(show['venue'])}"{style_attr}{cancelled_attr}>
<div class="perf-info">
<div class="perf-title">{esc(show['title'])} <em>{esc(show.get('subtitle', ''))}</em></div>
<div class="perf-meta">
<span><span class="meta-icon">📅</span>{esc(format_show_date(show['date'], show['time']))}</span>
<span><span class="meta-icon">📍</span>{esc(show['venue'])}</span>{city_html}
</div>
<div class="perf-cast">
<strong>主演：</strong>{cast_html}<br/>
<strong>演出单位：</strong>{esc(show.get('troupe', ''))}
        </div>
</div>
<div class="perf-side">
{tags_html}
{buy_btn_html}
<div class="perf-price">{price_html}</div></div>

</div>"""


def is_show_visible(show, today):
    """判断演出是否应该显示（超过一周的已演剧目不再保留；取消演出同样适用）"""
    try:
        show_date = datetime.strptime(show['date'], '%Y-%m-%d')
    except (ValueError, KeyError):
        return True  # 日期解析失败则保留
    week_ago = today - timedelta(days=7)
    return show_date >= week_ago


def generate_star_cards(shows, today):
    """生成陆志艳特别关注区的卡片 HTML"""
    star_shows = [s for s in shows if s['is_star'] and is_show_visible(s, today)]
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
    month_shows = [s for s in shows if not s['is_star'] and s['date'].startswith(f"2026-{month:02d}") and is_show_visible(s, today)]
    month_shows.sort(key=lambda s: (s['date'], s['time']))
    
    cards = [generate_card_html(show, today) for show in month_shows]
    return "\n".join(cards)


def generate_perf_dates(shows, today):
    """生成 PERF_DATES JS 对象（过滤超过一周的已演剧目）"""
    visible_shows = [s for s in shows if is_show_visible(s, today)]
    dates = {}
    for show in visible_shows:
        d = show['date']
        if d not in dates:
            dates[d] = []
        dates[d].append(show['id'])
    
    lines = []
    for d in sorted(dates.keys()):
        ids = ', '.join(f'"{sid}"' for sid in dates[d])
        lines.append(f'  "{d}": [{ids}],')
    
    return "{\n" + "\n".join(lines) + "\n}"

def generate_star_ids(shows, today):
    """生成 STAR_IDS JS 数组（过滤超过一周的已演剧目）"""
    visible_shows = [s for s in shows if s['is_star'] and is_show_visible(s, today)]
    star_ids = [s['id'] for s in visible_shows]
    ids_str = ', '.join(f'"{sid}"' for sid in star_ids)
    return f'[{ids_str}]'


def generate_event_cards(events, today):
    """生成非售票活动卡片（访谈 / 讲座 / 见面会），与演出卡片视觉区分"""
    events = [e for e in events if is_show_visible(e, today)]
    events.sort(key=lambda s: (s['date'], s.get('time', '00:00')))
    
    cards = []
    for ev in events:
        card_class = compute_card_class(ev['date'], today)
        classes = "perf-card event-card"
        if card_class:
            classes += f" {card_class}"
        
        etype = ev.get('event_type', '活动')
        style = EVENT_TYPE_STYLE.get(etype, EVENT_TYPE_STYLE['活动'])
        
        city_html = ""
        if ev.get('city'):
            city_html = f'\n<span><span class="meta-icon">🏙️</span>{esc(ev["city"])}</span>'

        # 主办 / 嘉宾（活动没有"主演/演出单位"），均转义
        info_parts = []
        if ev.get('host'):
            info_parts.append(f'<strong>主办：</strong>{esc(ev["host"])}')
        if ev.get('guest'):
            info_parts.append(f'<strong>嘉宾：</strong>{esc(ev["guest"])}')
        cast_html = "<br/>".join(info_parts) if info_parts else "详情以官方公布为准"

        price = ev.get('price', '免费 / 凭邀请')
        url_html = ""
        if ev.get('url'):
            url_html = f'<a class="event-link" href="{esc(ev["url"])}" target="_blank" rel="noopener noreferrer">🔗 公众号原文</a>'
        note_html = ""
        if ev.get('note'):
            note_html = f'<div class="event-note">📝 {esc(ev["note"])}</div>'

        cards.append(f"""<div class="{classes}" data-date="{esc(ev.get('date',''))}" data-id="{esc(ev['id'])}" data-time="{esc(ev.get('time',''))}" data-title="{esc(ev['title'])}" data-venue="{esc(ev.get('venue',''))}" data-event="{esc(etype)}">
<div class="perf-info">
<div class="perf-title">{esc(ev['title'])} <em>{esc(ev.get('subtitle', ''))}</em></div>
<div class="perf-meta">
<span><span class="meta-icon">📅</span>{esc(format_show_date(ev['date'], ev.get('time','')) if ev.get('date') else '日期待确认')}</span>
<span><span class="meta-icon">📍</span>{esc(ev.get('venue',''))}</span>{city_html}
</div>
<div class="perf-cast">
{cast_html}
</div>
{note_html}
</div>
<div class="perf-side">
<span class="event-tag" style="background:{style['bg']};color:{style['fg']};">{esc(etype)}</span>{('<span class="event-auto">🔄 自动发现</span>' if ev.get('auto') else '')}
<button class="buy-btn" onclick="toggleBought(this)"><span class="btn-icon">🎟️</span><span class="btn-text">标记已购</span></button>
<div class="perf-price">{esc(price)}</div>
{url_html}
</div>
</div>""")
    
    return "\n".join(cards)


def generate_leads_section():
    """渲染公众号待核对线索（自动发现但未能解析正文的候选）"""
    p = Path("wechat_leads.json")
    if not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    leads = data.get("leads", [])
    if not leads:
        return ""
    items = []
    for ld in leads[:15]:
        title = ld.get("title", "")
        acct = ld.get("account", "")
        url = ld.get("sogou_url", "")
        items.append(
            f'<div class="lead-item">· <span class="lead-title">{html.escape(html.unescape(title))}</span> '
            f'<span class="lead-acct">（{acct}）</span> '
            f'<a class="lead-link" href="{html.escape(url)}" target="_blank" rel="noopener">🔎 核对</a></div>'
        )
    return (
        '<div class="lead-box">\n'
        f'<div class="lead-head">🔎 公众号待核对线索（{len(leads)} 条）· 自动发现但未解析成功，请点击核对</div>\n'
        f'{"".join(items)}\n'
        '</div>'
    )


# ============================================================
# 智能提醒生成（基于历史对比）
# ============================================================
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
        role = ""
        role_match = re.search(r'陆志艳[）)）]?[（(]([^）)]+)', s['cast'])
        if role_match:
            role = f"（饰{role_match.group(1)}）"
        elif "陆志艳" in s['cast']:
            role_match2 = re.search(r'陆志艳[：:]\s*(\S+)', s['cast'])
            if role_match2:
                role = f"（饰{role_match2.group(1)}）"
        
        title_short = clean_title(s['title'])
        venue_short = s['venue'].replace('上海', '').replace('大剧院', '').replace('·大剧场', '').replace('·小剧场', '').replace('·戏·聚空间', '')
        parts.append(f"{dt.month}月{dt.day}日{venue_short}《{title_short}》{role}")
    return " → ".join(parts)


def generate_smart_alerts(shows, today, new_shows, cancelled_shows=None):
    """高优提醒：临场行动视角（今日 / 明日 / 本周临近 / 特别关注 / 主题巡演）。
    变更类信息（新增 / 取消）由「新动态」栏负责，本栏不重复，避免两栏内容冲突。"""
    lines = []
    today_str = date_str(today)
    tomorrow_str = date_str(today + timedelta(days=1))
    week_ahead = date_str(today + timedelta(days=7))

    today_shows = [s for s in shows if s['date'] == today_str and not s.get('cancelled')]
    tomorrow_shows = [s for s in shows if s['date'] == tomorrow_str and not s.get('cancelled')]
    week_shows = [s for s in shows if today_str < s['date'] <= week_ahead and not s.get('cancelled')]
    star_shows = [s for s in shows if s['is_star'] and s['date'] >= today_str and not s.get('cancelled')]
    tour_shows = [s for s in shows if s['date'].startswith(('2026-08', '2026-09')) and
                  any(c in s.get('city', '') + s.get('venue', '') for c in ['北京', '天津', '廊坊'])]

    # 去重：每场演出只在最紧急的分区出现一次（今日 > 明日 > 本周 > 星 > 巡演）
    used = set()
    for s in today_shows + tomorrow_shows + week_shows:
        used.add(s['id'])
    star_only = [s for s in star_shows if s['id'] not in used]
    tour_only = [s for s in tour_shows if s['id'] not in used]

    # 概览：先给结论，体现"质量感"
    has_any = today_shows or tomorrow_shows or week_shows or star_only or tour_only
    if has_any:
        bits = []
        if today_shows:
            bits.append(f"今日 {len(today_shows)} 场")
        if tomorrow_shows:
            bits.append(f"明日 {len(tomorrow_shows)} 场")
        if week_shows:
            bits.append(f"本周内 {len(week_shows)} 场")
        if star_only:
            bits.append(f"陆志艳 {len(star_only)} 场")
        lines.append(f"<strong>📌 需关注：{' · '.join(bits)}</strong><br/><br/>")
    else:
        lines.append("· 近期无临近演出，可从容规划 ✨<br/>")
        return "\n      ".join(lines)

    # 今日开演
    if today_shows:
        lines.append(f"<strong>🎭 今日开演</strong>（{today_str}）：<br/>")
        for show in today_shows:
            title_clean = clean_title(show['title'])
            star_mark = " ⭐" if show['is_star'] else ""
            lines.append(f"  · {esc(show['venue'])}《{esc(title_clean)}》{star_mark}<br/>")
        lines.append("<br/>")

    # 明日开演
    if tomorrow_shows:
        lines.append(f"<strong>⏰ 明日开演</strong>（{tomorrow_str}）：<br/>")
        for show in tomorrow_shows:
            title_clean = clean_title(show['title'])
            star_mark = " ⭐" if show['is_star'] else ""
            lines.append(f"  · {esc(show['venue'])}《{esc(title_clean)}》{star_mark}<br/>")
        lines.append("<br/>")

    # 本周临近（购票从速）
    if week_shows:
        lines.append(f"<strong>📅 本周临近</strong>（购票从速）：<br/>")
        for show in week_shows[:5]:
            dt = datetime.strptime(show['date'], "%Y-%m-%d")
            days_until = (dt - today).days
            title_clean = clean_title(show['title'])
            lines.append(f"  · {dt.month}月{dt.day}日（{days_until}天后）{esc(show['venue'])}《{esc(title_clean)}》<br/>")
        if len(week_shows) > 5:
            lines.append(f"  ... 还有 {len(week_shows) - 5} 场<br/>")
        lines.append("<br/>")

    # 陆志艳近期（特别关注）
    if star_only:
        lines.append(f"<strong>⭐ 陆志艳近期</strong>（特别关注）：<br/>")
        for show in star_only:
            dt = datetime.strptime(show['date'], "%Y-%m-%d")
            days_until = (dt - today).days
            title_clean = clean_title(show['title'])
            if days_until == 0:
                time_hint = "今日开演"
            elif days_until == 1:
                time_hint = "明日开演"
            else:
                time_hint = f"还剩 {days_until} 天"
            lines.append(f"  · {dt.month}月{dt.day}日 {esc(show['venue'])}《{esc(title_clean)}》— {time_hint}<br/>")
        lines.append("<br/>")

    # 主题巡演
    if tour_only:
        played = len([s for s in tour_shows if s['date'] < today_str])
        upcoming_t = len([s for s in tour_shows if s['date'] >= today_str])
        lines.append(f"<strong>🚄 京津冀巡演进行中</strong>（共 {len(tour_shows)} 场，已演 {played} / 剩余 {upcoming_t}）：<br/>")
        for show in tour_only[:4]:
            dt = datetime.strptime(show['date'], "%Y-%m-%d")
            title_clean = clean_title(show['title'])
            lines.append(f"  · {dt.month}月{dt.day}日 {esc(show['venue'])}《{esc(title_clean)}》<br/>")
        if len(tour_only) > 4:
            lines.append(f"  ... 还有 {len(tour_only) - 4} 场<br/>")
        lines.append("<br/>")

    return "\n      ".join(lines)


def generate_smart_news(shows, today, new_shows, cancelled_shows=None):
    """新动态：变更摘要（最近新上线 / 开票 / 演出 / 取消的概括）。
    与「高优提醒」分工明确：本栏只讲数据的变化，不重复临场行动信息。"""
    lines = []
    today_str = date_str(today)
    yesterday_str = date_str(today - timedelta(days=1))
    cancelled_shows = cancelled_shows or []

    # === 总括：本次数据更新（新增 / 取消）===
    if new_shows or cancelled_shows:
        parts = []
        if new_shows:
            parts.append(f"新增 {len(new_shows)} 场")
        if cancelled_shows:
            parts.append(f"官宣取消 {len(cancelled_shows)} 场")
        lines.append(f"<strong>🔔 本次数据更新：{' · '.join(parts)}</strong><br/><br/>")

    # === 新增（新上线 / 开票）===
    if new_shows:
        lines.append(f"<strong>🆕 新上线 / 开票 {len(new_shows)} 场</strong>（对比昨日）：<br/>")
        for show in new_shows[:5]:
            try:
                dt = datetime.strptime(show['date'], "%Y-%m-%d")
                date_label = f"{dt.month}月{dt.day}日"
            except (ValueError, KeyError):
                date_label = "日期待确认"
            title_clean = clean_title(show['title'])
            etype = show.get('event_type', '')
            etype_prefix = f"【{etype}】" if etype and etype != '演出' else ""
            price_info = ""
            if show.get('price') and show['price'] != '以场馆公布为准':
                price_info = f" — {esc(show['price'])}"
            lines.append(f"  · {esc(show['city'] or show['venue'])}《{etype_prefix}{esc(title_clean)}》（{date_label}）{price_info}<br/>")
        if len(new_shows) > 5:
            lines.append(f"  ... 还有 {len(new_shows) - 5} 场<br/>")
        lines.append("<br/>")

    # === 官宣取消 ===
    if cancelled_shows:
        lines.append(f"<strong>⚠️ 官宣取消 {len(cancelled_shows)} 场</strong>：<br/>")
        for show in cancelled_shows[:5]:
            try:
                dt = datetime.strptime(show['date'], "%Y-%m-%d")
                date_label = f"{dt.month}月{dt.day}日"
            except (ValueError, KeyError):
                date_label = "日期待确认"
            title_clean = clean_title(show['title'])
            lines.append(f"  · {esc(show['venue'])}《{esc(title_clean)}》（{date_label}）已取消<br/>")
        if len(cancelled_shows) > 5:
            lines.append(f"  ... 还有 {len(cancelled_shows) - 5} 场<br/>")
        lines.append("<br/>")

    # === 昨日演出回顾（最近"演出"过）===
    yesterday_shows = [s for s in shows if s['date'] == yesterday_str]
    if yesterday_shows:
        lines.append(f"<strong>✅ 昨日演出</strong>（{yesterday_str}）：<br/>")
        for show in yesterday_shows:
            title_clean = clean_title(show['title'])
            lines.append(f"  · {esc(show['venue'])}《{esc(title_clean)}》已上演<br/>")
        lines.append("<br/>")

    if not lines:
        lines.append("· 数据已是最新，暂无新动态。<br/>")

    return "\n      ".join(lines)


# ============================================================
# 主函数
# ============================================================
def main():
    # 读取数据
    data = json.loads(Path("shows.json").read_text(encoding="utf-8"))
    shows = data['shows']
    
    today = get_today()
    
    # 过滤超过一周的已演剧目
    week_ago_str = date_str(today - timedelta(days=7))
    visible_shows = [s for s in shows if is_show_visible(s, today)]
    hidden_count = len(shows) - len(visible_shows)
    if hidden_count > 0:
        print(f"  🗂️ 已隐藏 {hidden_count} 场超过一周的已演剧目（{week_ago_str} 之前）")
    
    # 读取历史数据（用于对比）
    print("\n📊 加载历史数据...")
    previous_shows = load_previous_shows()
    new_shows = find_new_shows(shows, previous_shows)
    cancelled_shows = find_cancelled_shows(shows, previous_shows)
    if cancelled_shows:
        print(f"  ⚠️ 发现 {len(cancelled_shows)} 场新官宣取消：")
        for show in cancelled_shows:
            print(f"    - {show['date']} {show['title']} @ {show['venue']}")
    elif previous_shows:
        print("  ✓ 无新官宣取消")
    
    if new_shows:
        print(f"  🆕 发现 {len(new_shows)} 场新增演出：")
        for show in new_shows:
            print(f"    - {show['date']} {show['title']} @ {show['venue']}")
    else:
        print("  ✓ 无新增演出（数据与昨日一致）")

    # 落盘新增演出，供 workflow 推送通知（Server酱 / 其他渠道）
    try:
        ns_dump = [{
            "id": s.get("id", ""),
            "date": s.get("date", ""),
            "time": s.get("time", ""),
            "title": s.get("title", ""),
            "subtitle": s.get("subtitle", ""),
            "venue": s.get("venue", ""),
            "city": s.get("city", ""),
            "price": s.get("price", ""),
        } for s in new_shows]
        Path("new_shows.json").write_text(
            json.dumps(ns_dump, ensure_ascii=False, indent=2), encoding="utf-8")
        if ns_dump:
            print(f"  📤 已写出 new_shows.json（{len(ns_dump)} 场，供通知推送）")
    except Exception as e:
        print(f"  ⚠️ 写出 new_shows.json 失败(忽略): {e}")

    # 分离演出与活动（访谈/讲座/见面会）
    performances = [s for s in shows if not is_event(s)]
    events = [s for s in shows if is_event(s)]
    
    # 计算统计
    total = len(shows)
    star_count = len([s for s in shows if s['is_star']])
    cities = set(s['city'] for s in shows if s.get('city'))
    
    # 生成内容
    report_date = format_report_date(today)
    report_date_badge = format_report_date_badge(today)
    data_updated = format_data_updated()
    
    star_cards = generate_star_cards(performances, today)
    july_cards = generate_month_cards(performances, today, 7)
    aug_cards = generate_month_cards(performances, today, 8)
    sep_cards = generate_month_cards(performances, today, 9)
    event_cards = generate_event_cards(events, today)
    leads_html = generate_leads_section()
    event_section = ""
    if event_cards.strip() or leads_html.strip():
        event_section = (
            '<!-- ===== 🎤 名家活动 ===== -->\n'
            '<h2 class="section-title"><span class="section-icon">🎤</span> 名家活动 · 访谈讲座见面会</h2>\n'
            '<div class="event-grid">\n'
            f'{event_cards}\n'
            '</div>\n'
            f'{leads_html}'
        )
    
    perf_dates_json = generate_perf_dates(shows, today)
    star_ids_json = generate_star_ids(performances, today)
    
    # 生成智能提醒（基于历史对比；演出与活动分别处理）
    alert_urgent = generate_smart_alerts(performances, today, new_shows, cancelled_shows)
    alert_new = generate_smart_news(performances, today, new_shows, cancelled_shows)
    
    # 读取模板并替换
    template = Path("template.html").read_text(encoding="utf-8")
    
    # 生成备注信息区块（静态内容，不需要动态替换）
    notes_section = """  <!-- ===== 📌 备注 ===== -->
  <h2 class="section-title"><span class="section-icon">📌</span> 备注信息</h2>
  <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px 24px;font-size:14px;color:var(--text-muted);line-height:2;">
    · 上海越剧院2026年共有<strong style="color:var(--gold-light)">百余场</strong>演出计划，全年聚焦经典传承、宗师纪念（王文娟诞辰100周年）、流派弘扬三大方向。<br>
    · 新编越剧《华山奇缘》拟于盛夏首演（具体排期待定），将以《沉香太子全传》为基础改编。<br>
    · 2026年末上海越剧院新址将正式启用，届时举办开幕系列演出。<br>
    · 上海越剧院第十代青年演员（东方卫视《越动青春》选手）将推出专场演唱会（时间待定）。<br>
    · 天蟾逸夫舞台购票：大麦网 / 天蟾小程序<br>
    · 宛平剧院购票：大麦网 / 宛平剧院官网<br>
    · 临港演艺中心购票：大麦网<br>
    · 太仓大剧院购票：大麦网 / 东方演出网<br>
    · 京津冀巡演：各场馆官方渠道购票（海报扫码/北大讲堂售票处/吉祥官网/天津文惠卡/国家大剧院等）。<br>
    · <strong style="color:var(--gold-light)">🎟️ 已购标记</strong>保存在浏览器本地，更新页面自动恢复。跨设备同步：<strong>📋 导出</strong>复制后发送到另一台设备 → <strong>📥 导入</strong>粘贴即可合并。
  </div>"""
    
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
        "{{EVENT_SECTION}}": event_section,
        "{{PERF_DATES_JSON}}": perf_dates_json,
        "{{STAR_IDS_JSON}}": star_ids_json,
        "{{ALERT_URGENT}}": alert_urgent,
        "{{ALERT_NEW}}": alert_new,
        "{{NOTES_SECTION}}": notes_section,
    }
    
    html = template
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    
    # ============================================================
    # PWA 支持：注入 manifest 链接、theme-color、SW 注册
    # ============================================================
    pwa_head_tags = """<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#c9a96e">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="越剧监控">
<link rel="apple-touch-icon" href="icon-180.png">
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="icon-512.png">"""
    
    if "manifest.json" not in html:
        html = html.replace("<head>", "<head>\n" + pwa_head_tags, 1)
        print("  ℹ️ PWA head tags injected")
    
    # PWA: SW 注册 + 自定义安装按钮（捕获 beforeinstallprompt 事件）
    pwa_sw_script = """<script>
// Service Worker 注册
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').then(function(reg) {
    console.log('SW registered:', reg.scope);
  }).catch(function(e) {
    console.log('SW registration failed:', e);
  });
}

// 自定义安装按钮：捕获 beforeinstallprompt 事件
var deferredPrompt = null;
window.addEventListener('beforeinstallprompt', function(e) {
  e.preventDefault();
  deferredPrompt = e;
  
  // 创建安装按钮
  var btn = document.createElement('div');
  btn.id = 'pwa-install-btn';
  btn.innerHTML = '<span>📱 安装到桌面</span>';
  btn.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:99999;background:linear-gradient(135deg,#c9a96e,#e0c88e);color:#0d0c0a;padding:12px 20px;border-radius:30px;font-size:14px;font-weight:700;box-shadow:0 4px 20px rgba(201,169,110,0.5);cursor:pointer;display:flex;align-items:center;gap:6px;animation:pwaPulse 2s ease-in-out infinite;';
  
  var style = document.createElement('style');
  style.textContent = '@keyframes pwaPulse{0%,100%{transform:scale(1);box-shadow:0 4px 20px rgba(201,169,110,0.5)}50%{transform:scale(1.05);box-shadow:0 6px 30px rgba(201,169,110,0.7)}}#pwa-install-btn:active{transform:scale(0.95)}';
  document.head.appendChild(style);
  
  btn.onclick = function() {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function(result) {
        if (result.outcome === 'accepted') {
          console.log('PWA installed!');
        }
        deferredPrompt = null;
        btn.remove();
      });
    }
  };
  
  document.body.appendChild(btn);
});

// 安装成功后隐藏按钮
window.addEventListener('appinstalled', function() {
  var btn = document.getElementById('pwa-install-btn');
  if (btn) btn.remove();
  console.log('PWA installed successfully');
});
</script>"""
    
    if "navigator.serviceWorker.register('sw.js')" not in html:
        html = html.replace("</body>", pwa_sw_script + "\n</body>")
        print("  ℹ️ PWA service worker registered")
    
    # 兜底：如果模板里既没有 {{NOTES_SECTION}} 占位符，也没有"备注信息"字样，
    # 则在 footer 前自动插入备注区块
    if "备注信息" not in html:
        # 在 <!-- ===== FOOTER ===== --> 之前插入
        footer_marker = "<!-- ===== FOOTER ===== -->"
        if footer_marker in html:
            html = html.replace(
                footer_marker,
                notes_section + "\n\n" + footer_marker
            )
        else:
            # 如果实在找不到 footer，就插在 </body> 之前
            html = html.replace("</body>", notes_section + "\n\n</body>")
        print("  ℹ️ 模板中未找到备注信息，已自动插入")
    
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
    print(f"\n✅ index.html 生成完成")
    print(f"   报告日期：{report_date}（{WEEKDAYS_CN[today.weekday()]}）")
    print(f"   演出场次：{total}（陆志艳 {star_count} 场）")
    print(f"   涉及城市：{len(cities)} 个")
    print(f"   数据时间：{data_updated}")


if __name__ == "__main__":
    main()
