#!/usr/bin/env python3
"""
wechat_events.py — 从公众号推文抓取「访谈 / 讲座 / 见面会」等非售票活动

目标账号（用户指定，一般只盯这两个）：
  - 宛平剧院
  - 天蟾逸夫舞台

两条数据通路：
  Tier A（稳定）：wechat_links.txt 里放着 mp.weixin.qq.com 文章链接，
                  直接抓取正文并结构化解析。最可靠，推荐日常使用。
  Tier B（best-effort）：搜狗微信搜索自动发现这两个号的近期相关推文。
                  搜狗反爬极强，经常被拦（审批页/验证码），所以这一层是
                  「尽力而为」：
                    · 能解析到正文的 → 生成「已确认」活动卡片；
                    · 被拦、拿不到正文的 → 只作为「待核对线索」单独列出
                      （带搜狗链接，不占日历、不填假日期），由用户点击核对。

解析结果：
  wechat_events.json  — 确认的活动（与 events.json 同 schema），进「名家活动」区
  wechat_leads.json  — 未解析成功的候选线索，单独展示「待核对」

全部网络操作均包裹 try/except，任何失败只打印警告，绝不中断主流程。
"""
import json
import re
import time
import html
import hashlib
import http.cookiejar
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from pathlib import Path

# ============================================================
# 配置
# ============================================================
WECHAT_ACCOUNTS = ["宛平剧院", "天蟾逸夫舞台"]

# 自动发现用的事件关键词（命中即视为活动类推文）
DISCOVERY_KEYWORDS = ["访谈", "讲座", "见面会", "活动"]

# 事件类型判定（按优先级，先命中先用）
EVENT_TYPE_MAP = [
    ("见面会", "见面会"),
    ("访谈", "访谈"),
    ("对谈", "访谈"),
    ("讲座", "讲座"),
    ("导赏", "讲座"),
    ("分享会", "讲座"),
    ("公开课", "讲座"),
    ("一戏一赏", "讲座"),
    ("赏析", "讲座"),
    ("雅集", "活动"),
    ("招募", "活动"),
    ("活动", "活动"),
]

# 已知场馆（用于从正文抽取场地）
KNOWN_VENUES = [
    "天蟾逸夫舞台", "上海天蟾逸夫舞台",
    "宛平剧院", "上海宛平剧院",
    "戏曲会客厅", "戏·聚空间", "B1小剧场", "大剧场",
]

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
SLEEP_BETWEEN = 3.0      # 请求间隔（秒），避免过快被拦
DISCOVERY_ENABLED = True  # 是否启用搜狗自动发现；设为 False 只走 Tier A 链接
MAX_LEADS = 25            # 待核对线索最多保留条数

# ============================================================
# 网络会话（带 cookie，模拟浏览器以兼容搜狗跳转）
# ============================================================
_cj = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))


def _get(url, ref="https://weixin.sogou.com/", timeout=25):
    """返回 (text, final_url, status)。失败抛异常。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": ref,
        },
    )
    resp = _opener.open(req, timeout=timeout)
    data = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        try:
            data = gzip.decompress(data)
        except Exception:
            pass
    return data.decode("utf-8", "ignore"), resp.geturl(), resp.status


def _clean(tag_text):
    t = re.sub(r"<[^>]+>", "", tag_text or "")
    return html.unescape(t).strip()


# ============================================================
# 搜狗微信自动发现（Tier B，best-effort）
# ============================================================
def discover_account_keyword(account, keyword):
    """搜索 account + keyword 的近期推文，返回候选列表（已按来源+关键词过滤）"""
    query = f"{account} {keyword}"
    url = "https://weixin.sogou.com/weixin?type=2&query=" + urllib.parse.quote(query)
    text, _, _ = _get(url)
    # 反爬/验证码/审批页 → 直接放弃本次发现
    if not text or any(k in text for k in ("antispider", "请输入验证码", "请确认您不是机器人")):
        print(f"    ⚠️ 搜狗拦截（{account}/{keyword}），跳过")
        return []
    # 解析结果项
    items = re.findall(r'<li id="sogou_vr_[^"]*"[^>]*>(.*?)</li>', text, re.S)
    results = []
    for it in items:
        tm = re.search(r"<h3>.*?<a[^>]*>(.*?)</a>", it, re.S)
        if not tm:
            continue
        title = _clean(tm.group(1))
        if not title:
            continue
        # 来源
        sp = re.search(r'class="s-p"[^>]*>(.*?)</', it, re.S)
        source = ""
        if sp:
            spt = _clean(sp.group(1))
            sm = re.search(r"来源[：:]\s*([^\s/]+)", spt)
            if sm:
                source = sm.group(1).strip("，。 ")
        # 只保留目标账号自己发的
        if not (account in source or account in title):
            continue
        # 摘要
        sn = re.search(r'class="txt-info"[^>]*>(.*?)</', it, re.S)
        snippet = _clean(sn.group(1)) if sn else ""
        # 必须真的在标题/摘要里提到事件词，避免把普通演出预告误判成活动
        if not any(kw in title or kw in snippet for kw in DISCOVERY_KEYWORDS):
            continue
        # wrapper 链接（需 html.unescape + 去空格才能用）
        hm = re.search(r'href="(/link\?url=[^"]+)"', it)
        wrapper = ""
        if hm:
            wrapper = "https://weixin.sogou.com" + html.unescape(hm.group(1)).replace(" ", "%20")
        results.append({
            "title": title,
            "source": source,
            "snippet": snippet,
            "wrapper_url": wrapper,
            "sogou_url": url,
            "account": account,
        })
    return results


# ============================================================
# 文章正文解析
# ============================================================
def resolve_article(wrapper_url):
    """经搜狗 wrapper 跳转到真实 mp.weixin 文章，返回 (标题, 日期ISO, 正文, 真实URL)"""
    text, final, _ = _get(wrapper_url)
    if not final.startswith("https://mp.weixin.qq.com"):
        return None  # 被审批页拦了，拿不到正文
    return _parse_mp(text, final)


def resolve_direct(url):
    """直接抓取 mp.weixin.qq.com 文章链接（Tier A，最稳）"""
    text, final, _ = _get(url)
    if "mp.weixin.qq.com" not in final:
        return None
    return _parse_mp(text, final)


def _parse_mp(text, url):
    """从公众号文章 HTML 抽取标题 / 发布日期 / 正文"""
    title = ""
    tm = re.search(r'id="activity-name"[^>]*>(.*?)</h1>', text, re.S)
    if tm:
        title = _clean(tm.group(1))
    else:
        tm = re.search(r'"msg_title"\s*:\s*"(.*?)"', text)
        if tm:
            title = html.unescape(tm.group(1))
    date_iso = None
    tsm = (re.search(r'var\s+ct\s*=\s*["\']?(\d{10})', text)
           or re.search(r'"ct"\s*:\s*"(\d{10})"', text)
           or re.search(r'publish_time\s*=\s*["\'](\d{10})', text))
    if tsm:
        try:
            date_iso = datetime.fromtimestamp(int(tsm.group(1))).strftime("%Y-%m-%d")
        except Exception:
            date_iso = None
    body = ""
    mc = re.search(r'id=["\']js_content["\'][^>]*>(.*?)</div>\s*</div>', text, re.S)
    if mc:
        body = _clean(mc.group(1))
    else:
        body = _clean(text)[:6000]
    return title, date_iso, body, url


# ============================================================
# 结构化字段抽取
# ============================================================
def extract_event_type(*texts):
    blob = " ".join(t for t in texts if t)
    for kw, etype in EVENT_TYPE_MAP:
        if kw in blob:
            return etype
    return None


def extract_date(text):
    if not text:
        return None
    m = re.search(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if m:
        return f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def extract_time(text):
    if not text:
        return ""
    m = re.search(r"(\d{1,2}:\d{2})", text)
    return m.group(1) if m else ""


def extract_venue(text):
    if not text:
        return ""
    for v in KNOWN_VENUES:
        if v in text:
            if "天蟾" in v:
                return "上海天蟾逸夫舞台"
            if "宛平" in v:
                return "上海宛平剧院"
            return v
    return ""


def parse_event(title, body, snippet, account):
    """综合标题/正文/摘要抽取活动；无事件关键词返回 None（避免把售票演出当活动）"""
    etype = extract_event_type(title, snippet, body[:3000])
    if not etype:
        return None
    date = extract_date(body) or extract_date(snippet) or extract_date(title)
    time_str = extract_time(body) or extract_time(snippet)
    venue = extract_venue((title or "") + " " + (body or "")[:2000]) or f"{account}（场地待确认）"
    return {
        "title": title or "公众号活动",
        "subtitle": f"{account} · 名家活动",
        "date": date or "",
        "time": time_str,
        "venue": venue,
        "city": "上海",
        "event_type": etype,
        "host": f"{account}（公众号）",
        "guest": "",
        "price": "免费 / 凭预约",
        "note": "",
        "is_star": False,
    }


def _event_id(ev):
    key = (ev.get("date", "") + "|" + ev.get("title", "") + "|" + ev.get("venue", "")).encode("utf-8")
    return "wx-" + hashlib.md5(key).hexdigest()[:10]


# ============================================================
# 候选 → 已确认活动 / 线索
# ============================================================
def build_from_candidate(c):
    """尝试解析正文；成功且确为活动 → 返回确认活动；否则返回 None（作为线索处理）"""
    wrapper = c.get("wrapper_url", "")
    if not wrapper:
        return None
    try:
        resolved = resolve_article(wrapper)
    except Exception:
        return None
    if not resolved:
        return None
    rtitle, rdate, rbody, rurl = resolved
    ev = parse_event(rtitle or c["title"], rbody, c.get("snippet", ""), c["account"])
    if not ev:
        return None
    ev["source_url"] = rurl
    ev["auto"] = True
    ev["status"] = "confirmed"
    ev["id"] = _event_id(ev)
    return ev


def candidate_to_lead(c):
    """被拦/解析失败的候选，转为待核对线索"""
    return {
        "title": c["title"],
        "account": c["account"],
        "sogou_url": c.get("sogou_url", ""),
        "found_at": datetime.now().strftime("%Y-%m-%d"),
    }


def build_from_link(url):
    """Tier A：用户提供的文章链接 → 确认活动"""
    try:
        resolved = resolve_direct(url)
    except Exception as e:
        print(f"    ⚠️ 链接解析失败 [{url[:50]}]: {e}")
        return None
    if not resolved:
        return None
    title, rdate, rbody, rurl = resolved
    account = ""
    for acc in WECHAT_ACCOUNTS:
        if acc in (title or "") or acc in (rbody or "")[:2000]:
            account = acc
            break
    account = account or "公众号"
    ev = parse_event(title, rbody, "", account)
    if not ev:
        return None  # 这是普通售票演出预告，不进活动区
    if not ev.get("date"):
        ev["date"] = rdate or ""
    ev["source_url"] = rurl
    ev["auto"] = True
    ev["status"] = "confirmed"
    ev["id"] = _event_id(ev)
    return ev


# ============================================================
# 链接文件（Tier A）
# ============================================================
def read_links():
    p = Path("wechat_links.txt")
    if not p.exists():
        return []
    links = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "mp.weixin.qq.com" in line:
            links.append(line)
    return links


# ============================================================
# 持久化
# ============================================================
def load_persisted():
    p = Path("wechat_events.json")
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {e["id"]: e for e in data.get("events", [])}
    except Exception:
        return {}


def save_persisted(events):
    out = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": "由 wechat_events.py 自动生成（搜狗微信 best-effort + 链接解析），勿手动编辑",
        "events": list(events.values()),
    }
    Path("wechat_events.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_leads():
    p = Path("wechat_leads.json")
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {f"{l['account']}|{l['title']}": l for l in data.get("leads", [])}
    except Exception:
        return {}


def save_leads(leads):
    items = list(leads.values())[:MAX_LEADS]
    out = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": "未解析成功的公众号候选，待用户核对；非确认活动",
        "leads": items,
    }
    Path("wechat_leads.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ============================================================
# 主入口
# ============================================================
def run():
    print("🤖 抓取公众号活动（宛平剧院 / 天蟾逸夫舞台）...")
    persisted = load_persisted()
    leads = load_leads()
    fresh_events = []
    fresh_leads = []

    # Tier B：搜狗自动发现
    if DISCOVERY_ENABLED:
        for account in WECHAT_ACCOUNTS:
            for kw in DISCOVERY_KEYWORDS:
                try:
                    cands = discover_account_keyword(account, kw)
                except Exception as e:
                    print(f"    ⚠️ 发现异常（{account}/{kw}）: {e}")
                    cands = []
                for c in cands:
                    ev = build_from_candidate(c)
                    if ev:
                        fresh_events.append(ev)
                    else:
                        fresh_leads.append(candidate_to_lead(c))
                time.sleep(SLEEP_BETWEEN)

    # Tier A：手动链接（最稳）
    for link in read_links():
        ev = build_from_link(link)
        if ev:
            fresh_events.append(ev)

    # 合并确认活动（按 id 去重）
    added_ev = 0
    for ev in fresh_events:
        eid = ev["id"]
        if eid not in persisted:
            persisted[eid] = ev
            added_ev += 1

    # 合并线索（按 账号|标题 去重，保留最近）
    added_lead = 0
    for ld in fresh_leads:
        k = f"{ld['account']}|{ld['title']}"
        if k not in leads:
            leads[k] = ld
            added_lead += 1

    save_persisted(persisted)
    save_leads(leads)
    print(f"  ✓ 公众号活动：确认 {added_ev} 条（累计 {len(persisted)}），待核对线索 {added_lead} 条（累计 {len(leads)}）")
    return added_ev


if __name__ == "__main__":
    run()
