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


def generate_smart_alerts(shows, today, new_shows):
    """生成智能提醒（基于历史对比，突出新增和紧急）"""
    lines = []
    today_str = date_str(today)
    
    # === 新增演出提醒（最有价值的信息）===
    if new_shows:
        lines.append(f"<strong>🔔 新发现 {len(new_shows)} 场演出</strong>（对比昨日数据）：<br/>")
        for i, show in enumerate(new_shows[:5]):  # 最多显示5场
            dt = datetime.strptime(show['date'], "%Y-%m-%d")
            days_until = (dt - today).days
            
            # 时间提示
            if days_until == 0:
                time_hint = " <span style='color:#ff6b6b;'>⚡ 今日开演！</span>"
            elif days_until == 1:
                time_hint = " <span style='color:#ffa07a;'>⏰ 明日开演</span>"
            elif days_until <= 3:
                time_hint = f" <span style='color:#ffd700;'>（还剩 {days_until} 天）</span>"
            elif days_until <= 7:
                time_hint = f"（{dt.month}月{dt.day}日，还剩 {days_until} 天）"
            else:
                time_hint = f"（{dt.month}月{dt.day}日）"
            
            # 票价信息
            price_info = ""
            if show.get('price') and show['price'] != '以场馆公布为准':
                price_info = f" — {show['price']}"
            
            title_clean = clean_title(show['title'])
            lines.append(f"  · {show['venue']}《{title_clean}》{time_hint}{price_info}<br/>")
        
        if len(new_shows) > 5:
            lines.append(f"  ... 还有 {len(new_shows) - 5} 场，详见下方列表<br/>")
        
        lines.append("<br/>")  # 空行分隔
    
    # === 今日开演 ===
    today_shows = [s for s in shows if s['date'] == today_str]
    if today_shows:
        lines.append(f"<strong>🎭 今日开演</strong>（{today_str}）：<br/>")
        for show in today_shows:
            title_clean = clean_title(show['title'])
            star_mark = " ⭐" if show['is_star'] else ""
            lines.append(f"  · {show['venue']}《{title_clean}》{star_mark}<br/>")
        lines.append("<br/>")
    
    # === 明日开演 ===
    tomorrow_str = date_str(today + timedelta(days=1))
    tomorrow_shows = [s for s in shows if s['date'] == tomorrow_str]
    if tomorrow_shows:
        lines.append(f"<strong>⏰ 明日开演</strong>（{tomorrow_str}）：<br/>")
        for show in tomorrow_shows:
            title_clean = clean_title(show['title'])
            star_mark = " ⭐" if show['is_star'] else ""
            lines.append(f"  · {show['venue']}《{title_clean}》{star_mark}<br/>")
        lines.append("<br/>")
    
    # === 陆志艳近期演出 ===
    star_shows = [s for s in shows if s['is_star'] and s['date'] >= today_str]
    if star_shows:
        lines.append(f"<strong>⭐ 陆志艳近期演出</strong>（共 {len(star_shows)} 场）：<br/>")
        for show in star_shows:
            dt = datetime.strptime(show['date'], "%Y-%m-%d")
            days_until = (dt - today).days
            title_clean = clean_title(show['title'])
            
            if days_until == 0:
                time_hint = "今日开演"
            elif days_until == 1:
                time_hint = "明日开演"
            else:
                time_hint = f"还剩 {days_until} 天"
            
            lines.append(f"  · {dt.month}月{dt.day}日 {show['venue']}《{title_clean}》— {time_hint}<br/>")
        lines.append("<br/>")
    
    # === 一周内演出提醒 ===
    week_ahead = date_str(today + timedelta(days=7))
    upcoming = [s for s in shows if today_str < s['date'] <= week_ahead and not s['is_star']]
    if upcoming and not new_shows:  # 如果有新增演出，已经在上面显示了
        lines.append(f"<strong>📅 一周内演出</strong>（{today_str} ~ {week_ahead}）：<br/>")
        for show in upcoming[:4]:
            dt = datetime.strptime(show['date'], "%Y-%m-%d")
            title_clean = clean_title(show['title'])
            days_until = (dt - today).days
            lines.append(f"  · {dt.month}月{dt.day}日（{days_until}天后）{show['venue']}《{title_clean}》<br/>")
        if len(upcoming) > 4:
            lines.append(f"  ... 还有 {len(upcoming) - 4} 场<br/>")
        lines.append("<br/>")
    
    if not lines:
        lines.append("· 暂无更新。<br/>")
    
    return "\n      ".join(lines)


def generate_smart_news(shows, today, new_shows):
    """生成今日新动态（更简洁，突出变化）"""
    lines = []
    today_str = date_str(today)
    yesterday_str = date_str(today - timedelta(days=1))
    
    # === 新增演出（最重要的动态）===
    if new_shows:
        lines.append(f"<strong>🔔 数据更新：新增 {len(new_shows)} 场演出</strong><br/>")
        for show in new_shows[:3]:
            dt = datetime.strptime(show['date'], "%Y-%m-%d")
            title_clean = clean_title(show['title'])
            lines.append(f"  · {show['city'] or show['venue']} 新增《{title_clean}》（{dt.month}月{dt.day}日）<br/>")
        if len(new_shows) > 3:
            lines.append(f"  ... 还有 {len(new_shows) - 3} 场<br/>")
        lines.append("<br/>")
    
    # === 今日开演 ===
    today_shows = [s for s in shows if s['date'] == today_str]
    if today_shows:
        lines.append(f"<strong>🎭 今日开演</strong>：<br/>")
        for show in today_shows:
            title_clean = clean_title(show['title'])
            lines.append(f"  · {show['venue']}《{title_clean}》<br/>")
        lines.append("<br/>")
    
    # === 昨日回顾 ===
    yesterday_shows = [s for s in shows if s['date'] == yesterday_str]
    if yesterday_shows:
        lines.append(f"<strong>✅ 昨日回顾</strong>：<br/>")
        for show in yesterday_shows:
            title_clean = clean_title(show['title'])
            lines.append(f"  · {show['venue']}《{title_clean}》已圆满演出<br/>")
        lines.append("<br/>")
    
    # === 京津冀巡演进度 ===
    aug_sep_shows = [s for s in shows if s['date'].startswith(('2026-08', '2026-09')) and 
                     any(city in s.get('city', '') + s.get('venue', '') for city in ['北京', '天津', '廊坊'])]
    if aug_sep_shows:
        total_aug_sep = len(aug_sep_shows)
        played = len([s for s in aug_sep_shows if s['date'] < today_str])
        upcoming_aug_sep = len([s for s in aug_sep_shows if s['date'] >= today_str])
        
        if upcoming_aug_sep > 0:
            lines.append(f"<strong>🚄 京津冀巡演进行中</strong>：<br/>")
            lines.append(f"  共 {total_aug_sep} 场（已演 {played} 场，剩余 {upcoming_aug_sep} 场）<br/>")
            lines.append(f"  场馆：北大/吉祥大戏院/国家大剧院/天津中国大戏院/廊坊壹佰剧院<br/>")
            lines.append("<br/>")
    
    # === 宛平剧院近期 ===
    wanping = [s for s in shows if '宛平' in s.get('venue', '') and s['date'] >= today_str]
    if wanping:
        lines.append(f"<strong>🎪 宛平剧院近期</strong>（共 {len(wanping)} 场）：<br/>")
        for show in wanping[:3]:
            dt = datetime.strptime(show['date'], "%Y-%m-%d")
            title_clean = clean_title(show['title'])
            lines.append(f"  · {dt.month}月{dt.day}日《{title_clean}》<br/>")
        if len(wanping) > 3:
            lines.append(f"  ... 还有 {len(wanping) - 3} 场<br/>")
        lines.append("<br/>")
    
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
    
    # 读取历史数据（用于对比）
    print("\n📊 加载历史数据...")
    previous_shows = load_previous_shows()
    new_shows = find_new_shows(shows, previous_shows)
    
    if new_shows:
        print(f"  🆕 发现 {len(new_shows)} 场新增演出：")
        for show in new_shows:
            print(f"    - {show['date']} {show['title']} @ {show['venue']}")
    else:
        print("  ✓ 无新增演出（数据与昨日一致）")
    
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
    
    # 生成智能提醒（基于历史对比）
    alert_urgent = generate_smart_alerts(shows, today, new_shows)
    alert_new = generate_smart_news(shows, today, new_shows)
    
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
        "{{PERF_DATES_JSON}}": perf_dates_json,
        "{{STAR_IDS_JSON}}": star_ids_json,
        "{{ALERT_URGENT}}": alert_urgent,
        "{{ALERT_NEW}}": alert_new,
        "{{NOTES_SECTION}}": notes_section,
    }
    
    html = template
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    
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
