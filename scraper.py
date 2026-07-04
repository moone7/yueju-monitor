#!/usr/bin/env python3
"""
scraper.py — 多数据源抓取脚本

抓取上海越剧院演出信息，输出 shows.json
数据源：
1. 东方演出网 (shanghaiyueju.df962388.com)
2. 戏曲百科 (wiki66.com) — 京津冀巡演页
3. 搜狐镜像 (yule.sohu.com) — 上海越剧院公众号文章
4. 大河票务 (dahepiao.com) — 票价/演员详情

容错：每个数据源独立 try/except，单个失败不阻塞
"""
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# 抑制 SSL 警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# 配置
# ============================================================
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}
TIMEOUT = 15
RETRIES = 2
SLEEP_BETWEEN = 1.5  # 秒，请求间隔

STAR_ACTOR = "陆志艳"

# 已知演出数据库（用于补全抓取不到的字段）
# 这些是之前已确认的演出，作为基础数据
KNOWN_SHOWS = [
    # 7月
    {"id":"p01","date":"2026-07-03","time":"19:30","title":"越剧《珍珠塔》","subtitle":"陆派看家大戏 · 上海越剧院一团","venue":"杭州胜利剧院","city":"杭州","cast":"徐标新（方卿）、邓华蔚（陈翠娥）、周燕儿（方朵花）","troupe":"上海越剧院一团","price":"¥180 起","is_star":False},
    {"id":"p02","date":"2026-07-03","time":"19:15","title":"越剧《重圆记》","subtitle":"宁波首演 · 上海越剧院红楼团","venue":"宁波逸夫剧院","city":"宁波","cast":"杨婷娜（徐德言）、李旭丹（乐昌）、王清（杨素）、陈欣雨（红拂）","troupe":"上海越剧院红楼团","price":"¥80 — 580","is_star":False},
    {"id":"p03","date":"2026-07-04","time":"19:30","title":"越剧《红楼梦》","subtitle":"尹袁版 · 杭州站","venue":"杭州胜利剧院","city":"杭州","cast":"王清/郭茜云（贾宝玉）、方亚芬/俞景岚（林黛玉）","troupe":"上海越剧院一团","price":"¥180/280/380/480/580","is_star":False},
    {"id":"p04","date":"2026-07-04","time":"19:15","title":"大型神话越剧《追鱼》","subtitle":"宁波站","venue":"宁波逸夫剧院","city":"宁波","cast":"杨婷娜（张珍）、忻雅琴（鲤鱼精）","troupe":"上海越剧院红楼团","price":"¥80/180/280/380/480/580","is_star":False},
    {"id":"lzy-01","date":"2026-07-09","time":"19:30","title":"越剧《红楼梦》","subtitle":"徐王版 · 2026广州艺术季","venue":"广州红线女大剧院","city":"广州","cast":"俞果（贾宝玉）、陆志艳（林黛玉）","troupe":"上海越剧院三团 · 广州艺术季重点展演","price":"¥80 — 480","is_star":True},
    {"id":"p05","date":"2026-07-10","time":"19:30","title":"越剧《梁山伯与祝英台》","subtitle":"范傅版 · 2026广州艺术季","venue":"广州红线女大剧院","city":"广州","cast":"董心心（梁山伯）、杨韵儿（祝英台）、潘锡丹（祝公远）","troupe":"上海越剧院三团 · 广州艺术季","price":"¥80 — 480","is_star":False},
    {"id":"p06","date":"2026-07-13","time":"19:15","title":"越剧《红楼梦》","subtitle":"徐王版 · 宛平驻场","venue":"上海宛平剧院·大剧场","city":"上海","cast":"王婉娜（贾宝玉）、李旭丹（林黛玉）","troupe":"上海越剧院红楼团","price":"¥80 — 380","is_star":False},
    {"id":"p07","date":"2026-07-14","time":"19:15","title":"越剧《梁山伯与祝英台》","subtitle":"范傅版 · 宛平驻场","venue":"上海宛平剧院·大剧场","city":"上海","cast":"王舒雯（梁山伯）、王婕（祝英台）、吴群（祝公远）","troupe":"上海越剧院红楼团","price":"¥80 — 380","is_star":False},
    {"id":"p08","date":"2026-07-15","time":"13:00","title":"越剧《梁山伯与祝英台》","subtitle":"文化惠民 · 社区展演","venue":"航头镇","city":"上海","cast":"","troupe":"上海越剧院红楼团 · 基层惠民演出","price":"公益/免费","is_star":False},
    {"id":"p09","date":"2026-07-18","time":"14:00","title":"越剧小戏《渔光曲》《自古英雄出少年》《新生》","subtitle":"","venue":"太仓大剧院","city":"太仓","cast":"冯军/王婉娜/姚磊、赵一兰/姚磊/张艾嘉、李旭丹/裘隆/冯军等","troupe":"上海越剧院","price":"全场 ¥50","is_star":False},
    {"id":"p10","date":"2026-07-22","time":"19:15","title":"小剧场越剧《张骞使西·三别三行》","subtitle":"丝路史诗","venue":"上海宛平剧院·小剧场","city":"上海","cast":"徐标新（张骞）、徐晓飞（匈奴女）、裘隆（汉武帝）、姚磊（甘父）、顾爱军（伊稚斜）","troupe":"上海越剧院一团","price":"¥80 / 180 / 280","is_star":False},
    {"id":"p11","date":"2026-07-23","time":"19:15","title":"小剧场越剧《张骞使西·三别三行》","subtitle":"丝路史诗","venue":"上海宛平剧院·小剧场","city":"上海","cast":"徐标新（张骞）、徐晓飞（匈奴女）、裘隆（汉武帝）","troupe":"上海越剧院一团","price":"¥80 / 180 / 280","is_star":False},
    {"id":"lzy-02","date":"2026-07-25","time":"14:30","title":"新编历史故事剧《虞美人》","subtitle":"经典复排 · 王派传承","venue":"上海临港演艺中心","city":"上海 · 临港","cast":"忻雅琴（虞姬）、王柔桑（项羽）、吴群（张良）、吴佳燕（范增）、陆志艳（无邪）","troupe":"上海越剧院 · 纪念越剧诞生120周年 · 复排剧目","price":"¥80 — 380","is_star":True},
    {"id":"p12","date":"2026-07-28","time":"19:15","title":"越剧《红楼梦》","subtitle":"尹袁版 · 蟾桂常青系列","venue":"上海天蟾逸夫舞台","city":"上海","cast":"郭茜云（贾宝玉）、俞景岚（林黛玉）","troupe":"上海越剧院一团","price":"¥80 — 380","is_star":False},
    {"id":"p13","date":"2026-07-29","time":"19:15","title":"越剧《梁山伯与祝英台》","subtitle":"袁范版 · 蟾桂常青系列","venue":"上海天蟾逸夫舞台","city":"上海","cast":"斯钰林（梁山伯）、徐晓飞（祝英台）、金烨（祝公远）","troupe":"上海越剧院一团","price":"¥80 — 380","is_star":False},
    {"id":"p14","date":"2026-07-31","time":"19:15","title":"小剧场越剧《假如我不是嵇康》","subtitle":"魏晋风骨","venue":"上海宛平剧院·小剧场","city":"上海","cast":"王柔桑（嵇康）、吴佳燕（广陵仙子）、陈慧迪（长乐亭主）、潘锡丹、孙嘉蔚","troupe":"上海越剧院","price":"¥80 / 180 / 280","is_star":False},
    # 8月
    {"id":"p15","date":"2026-08-01","time":"19:15","title":"小剧场越剧《假如我不是嵇康》","subtitle":"魏晋风骨","venue":"上海宛平剧院·小剧场","city":"上海","cast":"王柔桑（嵇康）、吴佳燕（广陵仙子）、陈慧迪（长乐亭主）","troupe":"上海越剧院","price":"¥80 / 180 / 280","is_star":False},
    {"id":"p16","date":"2026-08-03","time":"19:15","title":"小剧场实验越剧《再生·缘》","subtitle":"沉浸式 · 全场无座","venue":"上海宛平剧院·戏·聚空间","city":"上海","cast":"忻雅琴（孟丽君）、王清（皇帝）、王柔桑（皇甫少华）","troupe":"上海越剧院","price":"¥180","is_star":False},
    {"id":"p17","date":"2026-08-04","time":"19:15","title":"小剧场实验越剧《再生·缘》","subtitle":"沉浸式","venue":"上海宛平剧院·戏·聚空间","city":"上海","cast":"忻雅琴（孟丽君）、王清（皇帝）、王柔桑（皇甫少华）","troupe":"上海越剧院","price":"¥180","is_star":False},
    {"id":"lzy-03","date":"2026-08-08","time":"19:00","title":"越剧《舞台姐妹》","subtitle":"纪念越剧诞生120周年 · 师生传承版","venue":"北京大学百周年纪念讲堂","city":"北京","cast":"竺春花：单仰萍、陆志艳 | 邢月红：俞果","troupe":"上海越剧院三团 · 时长约170分钟（含中场休息15分钟）","price":"校内 ¥40 — 240","is_star":True},
    {"id":"p18","date":"2026-08-09","time":"19:00","title":"越剧《孟丽君》","subtitle":"京津冀巡演","venue":"北京大学百周年纪念讲堂","city":"北京","cast":"孟丽君：单仰萍/忻雅琴 | 皇甫少华：王柔桑 | 皇帝：杨婷娜","troupe":"上海越剧院红楼团 · 时长150分钟","price":"校内 ¥40-240","is_star":False},
    {"id":"p19","date":"2026-08-11","time":"19:30","title":"越剧《西厢记》","subtitle":"京津冀巡演","venue":"北京吉祥大戏院","city":"北京","cast":"陈慧迪（崔莺莺）、王婉娜（张珙）、盛舒扬（红娘）、吴群（崔夫人）","troupe":"上海越剧院红楼团","price":"以戏院公布为准","is_star":False},
    {"id":"p20","date":"2026-08-12","time":"19:30","title":"越剧《孔雀东南飞》","subtitle":"京津冀巡演","venue":"北京吉祥大戏院","city":"北京","cast":"王柔桑（焦仲卿）、盛舒扬（刘兰芝）、吴佳燕（焦母）","troupe":"上海越剧院红楼团","price":"以场馆公布为准","is_star":False},
    {"id":"p21","date":"2026-08-15","time":"19:15","title":"越剧《红楼梦》","subtitle":"京津冀巡演","venue":"天津中国大戏院","city":"天津","cast":"杨婷娜（贾宝玉）、单仰萍/忻雅琴（林黛玉）","troupe":"上海越剧院红楼团（全女班）","price":"¥50 — 580","is_star":False},
    {"id":"p22","date":"2026-08-16","time":"19:15","title":"越剧《西厢记》","subtitle":"京津冀巡演","venue":"天津中国大戏院","city":"天津","cast":"陈慧迪（崔莺莺）、杨婷娜（张珙）、盛舒扬（红娘）、吴群（崔夫人）","troupe":"上海越剧院红楼团","price":"¥50 — 580","is_star":False},
    {"id":"p23","date":"2026-08-16","time":"19:30","title":"越剧《血手印》","subtitle":"嘉定月月有戏","venue":"上海保利大剧院-大剧场","city":"上海","cast":"","troupe":"上海越剧院 · 中国建设银行嘉定支行艺术普及专场","price":"¥80 — 380","is_star":False},
    {"id":"p24","date":"2026-08-18","time":"19:00","title":"越剧《孔雀东南飞》","subtitle":"京津冀巡演","venue":"河北廊坊壹佰剧院","city":"廊坊","cast":"王舒雯（焦仲卿）、王婕（刘兰芝）、吴佳燕（焦母）","troupe":"上海越剧院红楼团","price":"以场馆公布为准","is_star":False},
    {"id":"p25","date":"2026-08-19","time":"19:00","title":"越剧《孟丽君》","subtitle":"京津冀巡演","venue":"河北廊坊壹佰剧院","city":"廊坊","cast":"忻雅琴（孟丽君）、王柔桑（皇甫少华）、杨婷娜（皇帝）","troupe":"上海越剧院红楼团","price":"以场馆公布为准","is_star":False},
    {"id":"p26","date":"2026-08-22","time":"19:30","title":"越剧《甄嬛》","subtitle":"京津冀巡演 · 全本首登国家大剧院","venue":"北京国家大剧院·戏剧场","city":"北京","cast":"李旭丹（甄嬛）、杨婷娜（皇帝）、王清（清河王）、史燕彬（沈眉庄）、王柔桑（温实初）、裘丹莉（华贵妃）、陈慧迪（安陵容）、王婕（槿汐）","troupe":"上海越剧院红楼团 · 上下本需分别购票","price":"¥100 — 580","is_star":False},
    {"id":"p27","date":"2026-08-23","time":"19:30","title":"越剧《甄嬛》","subtitle":"京津冀巡演 · 全本首登国家大剧院","venue":"北京国家大剧院·戏剧场","city":"北京","cast":"李旭丹（甄嬛）、杨婷娜（皇帝）、王清（清河王）、裘丹莉（华贵妃）","troupe":"上海越剧院红楼团 · 上下本需分别购票","price":"¥100 — 580","is_star":False},
    # 9月
    {"id":"p28","date":"2026-09-05","time":"14:30","title":"大型神话越剧《追鱼》","subtitle":"京津冀巡演","venue":"北京艺术中心·戏剧场","city":"北京","cast":"杨婷娜（张珍）、忻雅琴（鲤鱼精）","troupe":"上海越剧院红楼团 · 纪念王文娟诞辰100周年复排剧目","price":"扫码购票","is_star":False},
    {"id":"p29","date":"2026-09-06","time":"14:30","title":"越剧《红楼梦》","subtitle":"京津冀巡演 · 收官场","venue":"北京艺术中心·戏剧场","city":"北京","cast":"王婉娜（贾宝玉）、李旭丹（林黛玉）","troupe":"上海越剧院红楼团","price":"扫码购票","is_star":False},
    {"id":"lzy-04","date":"2026-09-12","time":"19:30","title":"越剧《舞台姐妹》","subtitle":"百越文创第五届越剧优秀剧目邀请展 · 全本传承版","venue":"杭州蝴蝶剧场","city":"杭州","cast":"俞果（邢月红）、陆志艳（竺春花）","troupe":"上海越剧院三团 · 百越文创第五届越剧优秀剧目邀请展 · 时长约150分钟","price":"¥180 — 380","is_star":True},
]


# ============================================================
# HTTP 工具
# ============================================================
def fetch_url(url, encoding='utf-8'):
    """带重试的 HTTP 请求"""
    for attempt in range(RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
            if encoding:
                resp.encoding = encoding
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            if attempt < RETRIES:
                time.sleep(SLEEP_BETWEEN)
                continue
            print(f"  ⚠️ 抓取失败 [{url}]: {e}")
            return None
    return None


def parse_html(html_text):
    """解析 HTML"""
    return BeautifulSoup(html_text, 'html.parser')


# ============================================================
# 数据源 1: 东方演出网
# ============================================================
def scrape_df962388():
    """抓取东方演出网上海越剧演出列表"""
    print("📊 抓取东方演出网...")
    shows = []
    try:
        html = fetch_url("https://shanghaiyueju.df962388.com/")
        if not html:
            return shows
        soup = parse_html(html)
        
        # 查找演出列表项
        items = soup.select('a[href*="/yanchu/"]')
        for item in items:
            try:
                title_text = item.get_text(strip=True)
                href = item.get('href', '')
                if not title_text or '/yanchu/' not in href:
                    continue
                
                # 查找日期和票价信息
                parent = item.find_parent()
                if not parent:
                    continue
                parent_text = parent.get_text()
                
                # 提取日期
                date_match = re.search(r'(2026\.\d{2}\.\d{2})', parent_text)
                if not date_match:
                    continue
                date_raw = date_match.group(1).replace('.', '-')
                
                # 只保留未来演出
                if date_raw < datetime.now().strftime("%Y-%m-%d"):
                    continue
                
                # 提取场馆
                venue = ""
                venue_match = re.search(r'地点[：:]\s*([^\n]+)', parent_text)
                if venue_match:
                    venue = venue_match.group(1).strip()
                
                # 提取票价
                price = ""
                price_match = re.search(r'门票价格[：:]\s*([^\n]+)', parent_text)
                if price_match:
                    price = price_match.group(1).strip()
                
                shows.append({
                    "title": title_text,
                    "date": date_raw,
                    "venue": venue,
                    "price": price,
                    "source": "df962388",
                    "source_url": urljoin("https://shanghaiyueju.df962388.com/", href)
                })
            except Exception as e:
                continue
        
        print(f"  ✓ 东方演出网: {len(shows)} 条")
    except Exception as e:
        print(f"  ⚠️ 东方演出网抓取失败: {e}")
    
    return shows


# ============================================================
# 数据源 2: 戏曲百科 (wiki66.com)
# ============================================================
def scrape_wiki66():
    """抓取戏曲百科京津冀巡演页面"""
    print("📚 抓取戏曲百科...")
    shows = []
    try:
        html = fetch_url('https://wiki66.com/上海越剧院2026%E2%80%9C%E4%BA%AC%E6%B4%A5%E5%86%80%E2%80%9D%E5%B7%A1%E6%BC%94')
        if not html:
            return shows
        soup = parse_html(html)
        
        # 戏曲百科的页面结构：按日期列出演出
        # 查找包含日期和剧目的段落
        text = soup.get_text()
        
        # 用正则提取演出信息
        # 格式类似："2026年08月22日 ... 演出《甄嬛》... 李旭丹、杨婷娜..."
        pattern = re.compile(
            r'(2026年\d{1,2}月\d{1,2}日).*?演出.*?《([^》]+)》.*?([^\n]+)',
            re.DOTALL
        )
        
        for match in pattern.finditer(text):
            date_str = match.group(1)
            title = match.group(2)
            actors = match.group(3).strip()[:100]
            
            # 解析日期
            try:
                dt = datetime.strptime(date_str, "%Y年%m月%d日")
                date_iso = dt.strftime("%Y-%m-%d")
            except:
                continue
            
            shows.append({
                "title": f"越剧《{title}》",
                "date": date_iso,
                "cast": actors,
                "source": "wiki66",
                "source_url": 'https://wiki66.com/上海越剧院2026京津冀巡演'
            })
        
        print(f"  ✓ 戏曲百科: {len(shows)} 条")
    except Exception as e:
        print(f"  ⚠️ 戏曲百科抓取失败: {e}")
    
    return shows


# ============================================================
# 数据源 3: 搜狐镜像 (上海越剧院公众号)
# ============================================================
def scrape_sohu_mirror():
    """抓取搜狐镜像上的上海越剧院演出预告"""
    print("📱 抓取搜狐镜像（上越公众号）...")
    shows = []
    try:
        # 搜索最新的七月/八月演出预告
        urls = [
            "https://yule.sohu.com/a/1043882280_121124763",  # 七月演出预告
        ]
        
        for url in urls:
            html = fetch_url(url)
            if not html:
                continue
            soup = parse_html(html)
            text = soup.get_text()
            
            # 提取演出信息
            # 格式："时间：7月X日 19:15 地点：XXX 主演：XXX"
            pattern = re.compile(
                r'时间[：:]\s*(\d{1,2}月\d{1,2}日)\s*(\d{1,2}:\d{2}).*?地点[：:]\s*([^\n]+?)(?:\s*主演|$)',
                re.DOTALL
            )
            
            for match in pattern.finditer(text):
                date_part = match.group(1)
                time_part = match.group(2)
                venue = match.group(3).strip()
                
                # 转换日期
                try:
                    dt = datetime.strptime(f"2026年{date_part}", "%Y年%m月%d日")
                    date_iso = dt.strftime("%Y-%m-%d")
                except:
                    continue
                
                shows.append({
                    "date": date_iso,
                    "time": time_part,
                    "venue": venue,
                    "source": "sohu",
                    "source_url": url
                })
            
            time.sleep(SLEEP_BETWEEN)
        
        print(f"  ✓ 搜狐镜像: {len(shows)} 条")
    except Exception as e:
        print(f"  ⚠️ 搜狐镜像抓取失败: {e}")
    
    return shows


# ============================================================
# 数据源 4: 大河票务 (票价/演员详情)
# ============================================================
def scrape_dahepiao():
    """抓取大河票务的票价和演员信息"""
    print("🎫 抓取大河票务...")
    shows = []
    try:
        # 搜索上海越剧院相关演出
        html = fetch_url("https://www.dahepiao.com/yanchupiaowu1/hj/20210716208439.html")
        if not html:
            return shows
        soup = parse_html(html)
        text = soup.get_text()
        
        # 提取票价
        price_match = re.search(r'演出票价[：:]\s*([\d,]+)', text)
        price = price_match.group(1) if price_match else ""
        
        # 提取演员
        cast_section = re.search(r'【演员表】(.*?)【', text, re.DOTALL)
        cast = cast_section.group(1).strip()[:200] if cast_section else ""
        
        if price or cast:
            shows.append({
                "title": "越剧《红楼梦》",
                "date": "2026-07-04",
                "venue": "浙江胜利剧院",
                "price": price,
                "cast": cast,
                "source": "dahepiao",
                "source_url": "https://www.dahepiao.com/yanchupiaowu1/hj/20210716208439.html"
            })
        
        print(f"  ✓ 大河票务: {len(shows)} 条")
    except Exception as e:
        print(f"  ⚠️ 大河票务抓取失败: {e}")
    
    return shows


# ============================================================
# 合并与去重
# ============================================================
def merge_shows(scraped_shows, known_shows):
    """将抓取的数据与已知数据合并"""
    # 以已知数据为基础
    merged = {f"{s['date']}|{s['title']}|{s['venue']}": s.copy() for s in known_shows}
    
    # 建立日期+场馆的索引，用于模糊匹配
    date_venue_index = {}
    for key, show in merged.items():
        dv_key = f"{show['date']}|{show.get('venue', '')}"
        if dv_key not in date_venue_index:
            date_venue_index[dv_key] = []
        date_venue_index[dv_key].append(key)
    
    new_count = 0
    for scraped in scraped_shows:
        title = scraped.get('title', '')
        date = scraped.get('date', '')
        venue = scraped.get('venue', '')
        
        # 尝试精确匹配
        key = f"{date}|{title}|{venue}"
        
        # 尝试模糊匹配（日期+场馆）
        matched = False
        if not title and venue:
            # 搜狐镜像的情况：只有日期+场馆，没有标题
            dv_key = f"{date}|{venue}"
            # 也尝试变体（如"浙江胜利剧院" vs "杭州胜利剧院"）
            for dv, keys in date_venue_index.items():
                dv_date, dv_venue = dv.split('|', 1)
                if dv_date == date and (
                    dv_venue in venue or venue in dv_venue or
                    dv_venue.replace('浙江', '杭州') == venue or
                    dv_venue.replace('杭州', '浙江') == venue
                ):
                    # 匹配到了，补全信息
                    for k in keys:
                        existing = merged[k]
                        if not existing.get('time') and scraped.get('time'):
                            existing['time'] = scraped['time']
                    matched = True
                    break
        
        if matched:
            continue
        
        if key in merged:
            # 补全缺失字段
            existing = merged[key]
            if not existing.get('price') and scraped.get('price'):
                existing['price'] = scraped['price']
            if not existing.get('cast') and scraped.get('cast'):
                existing['cast'] = scraped['cast']
            if not existing.get('time') and scraped.get('time'):
                existing['time'] = scraped['time']
        else:
            # 检查是否是已知演出的变体（标题包含关系）
            is_variant = False
            for k, existing in merged.items():
                if existing['date'] == date and title and title in existing['title']:
                    is_variant = True
                    # 补全信息
                    if not existing.get('price') and scraped.get('price'):
                        existing['price'] = scraped['price']
                    if not existing.get('cast') and scraped.get('cast'):
                        existing['cast'] = scraped['cast']
                    break
            
            if not is_variant and date and title and len(title) > 2:
                # 真正的新演出
                new_count += 1
                print(f"  🆕 新发现: {date} {title} @ {venue}")
                merged[key] = {
                    "id": f"new-{new_count:03d}",
                    "date": date,
                    "time": scraped.get('time', ''),
                    "title": title,
                    "subtitle": "",
                    "venue": venue,
                    "city": scraped.get('city', ''),
                    "cast": scraped.get('cast', ''),
                    "troupe": "上海越剧院",
                    "price": scraped.get('price', '以场馆公布为准'),
                    "is_star": STAR_ACTOR in scraped.get('cast', ''),
                }
    
    return list(merged.values())


# ============================================================
# 主函数
# ============================================================
def main():
    print("=" * 60)
    print("🎭 越剧监控数据抓取")
    print(f"📅 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    all_scraped = []
    
    # 抓取各数据源
    all_scraped += scrape_df962388()
    time.sleep(SLEEP_BETWEEN)
    
    all_scraped += scrape_wiki66()
    time.sleep(SLEEP_BETWEEN)
    
    all_scraped += scrape_sohu_mirror()
    time.sleep(SLEEP_BETWEEN)
    
    all_scraped += scrape_dahepiao()
    
    print(f"\n📊 抓取汇总: {len(all_scraped)} 条原始数据")
    
    # 合并已知数据
    shows = merge_shows(all_scraped, KNOWN_SHOWS)
    
    # 排序
    shows.sort(key=lambda s: (s['date'], s.get('time', '00:00')))
    
    # 统计
    total = len(shows)
    star_count = len([s for s in shows if s.get('is_star')])
    cities = set(s.get('city', '') for s in shows if s.get('city'))
    
    output = {
        "metadata": {
            "report_date": "auto",
            "data_updated": "auto",
            "total_shows": total,
            "star_shows": star_count,
            "cities": len(cities),
            "scraped_at": datetime.now().isoformat(),
            "sources": ["df962388", "wiki66", "sohu", "dahepiao"],
        },
        "shows": shows
    }
    
    Path("shows.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    print(f"\n✅ shows.json 生成完成")
    print(f"   总场次: {total}（陆志艳 {star_count} 场）")
    print(f"   涉及城市: {len(cities)} 个")
    
    if not all_scraped:
        print("\n⚠️ 所有数据源抓取失败，使用已知数据兜底")


if __name__ == "__main__":
    main()
