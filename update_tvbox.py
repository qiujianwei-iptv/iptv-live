#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秋风影视 · 自有线路库生成器（v2：无上游，库即全部）

工作方式只有三步：
  1. 读 own_sites.json —— 自有线路库，唯一真相，站点全在这里（含自己的合并 jar 引用）
  2. 每天逐站做存活探测：
       * 站点 ext 里通常挂着几个备用域名，逐个测，哪个活就用哪个
         （这就是「失效了是不是换了域名/网址」的自动处理：换了的自动切到新域名）
       * 全死 → 失败计数 +1；连续 3 天全死才算真死
       * 真死：主流线路（4K/玩偶/茉莉/木偶/咕噜/快映/虎斑等）只停用留档，
               其余直接删除
  3. 生成 tvbox.json / tvbox_local.json，并把探测结果写回库

没有上游、没有合并、没有兜底快照。上游哪天跑了、换 jar 了，都跟这里无关。
自己的 jar 在仓库 jar/qf_spider_merged.jar，md5 固定，站点类全在里面。

往库里加线路：在 own_sites.json 的 xs.sites 里加一条即可，示例：
  {"key": "新站", "name": "新站 • 4K", "type": 3, "api": "csp_XxxGuard",
   "searchable": 1, "quickSearch": 1, "ext": {"site": ["https://主域名", "https://备用域名"]},
   "_self": true}
  加了 _self 的站不会被自动删除，也不会因为探测不到被当成失效处理。

探测范围说明：ext 里带 http 域名的站（约 50 个）每天实测；
ext 是 token 的网盘类站没有可测地址，只能靠自己的 jar 类完整性（类缺了自动停用）。
"""

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
import io
import zipfile

# ---- 自有合并 jar（自己仓库里的，固定 md5）----
QF_JAR_MD5 = "c58eed36c90d07e45348a2bfc6617a8b"
QF_JAR_URLS = [
    "https://gh-proxy.com/https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/jar/qf_spider_merged.jar",
    "https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/jar/qf_spider_merged.jar",
]

UA = "okhttp/3.14.9"
TIMEOUT = 60

# ---- 自有线路库 ----
LIB_FILE = "own_sites.json"

# ---- 存活探测 ----
PROBE_TIMEOUT = 8        # 单地址超时（秒）
PROBE_WORKERS = 16       # 并发线程
PROBE_FAIL_LIMIT = 3     # 连续失效这么多次：先从配置里撤下（停用留档）
PROBE_DELETE_LIMIT = 10  # 连续失效这么多天：才真正从库里删除（给足恢复窗口）
# 整轮探测存活率低于这个比例，判定为「本轮网络异常」，结果作废不计数
# （CI 跑在海外机房，到国内站偶尔大面积超时，不能拿这种结果当站点死了）
PROBE_MIN_ALIVE_RATE = 0.5
PROBE_MIN_SAMPLE = 10

# 主流线路：真死时只停用留档（等你自己补新地址），不删
PROTECTED_BRANDS = {"玩偶", "茉莉", "木偶", "咕噜", "快映", "虎斑",
                    "蜡笔", "闪电", "多多", "花卷", "种子", "小丑",
                    "指南", "爱盼", "即刻", "双星", "卡卡", "搬运", "热播", "云播"}

MIN_SITES = 60

# ---- 统一配置中心 ----
CONFIG_CENTER_API = "csp_Config"
UNIFIED_DROP_APIS = {"csp_PanConfigGuard", "csp_MyPanGuard"}
NO_SEARCH_APIS = {"csp_Config", "csp_MyDriveGuard"}

# ---- 自建采集站（drpy2 爬虫，规则全在自己仓库 js/ 下）----
GH_RAW = "https://gh-proxy.com/https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main"
OWN_CJ_SITES = [
    {"key": "ffzy_cj", "name": "非凡 • 高清", "type": 3,
     "api": "assets://js/lib/drpy2.min.js", "searchable": 1, "quickSearch": 1, "filterable": 0,
     "ext": GH_RAW + "/js/ffzy.js", "_self": True},
    {"key": "zy360_cj", "name": "360 • 高清", "type": 3,
     "api": "assets://js/lib/drpy2.min.js", "searchable": 1, "quickSearch": 1, "filterable": 0,
     "ext": GH_RAW + "/js/360zy.js", "_self": True},
    {"key": "cz4k_js", "name": "厂长 • 4K", "type": 3,
     "api": "assets://js/lib/drpy2.min.js", "searchable": 0, "quickSearch": 0, "filterable": 0,
     "ext": GH_RAW + "/js/4kcz.js", "_self": True},
]

# 库里没有直播源时的兜底
DEFAULT_LIVES = [
    {"name": "综合", "type": 0, "url": "http://193.123.86.190:14888/TV/iptv.php",
     "ua": "bingcha/1.1 (mianfeifenxiang)", "playerType": 2},
    {"name": "牛播一", "url": "http://127.0.0.1:9978/proxy?do=cctva", "timeZone": "Asia/Shanghai"},
    {"name": "Kimentanm", "type": 0,
     "url": "https://ghproxy.net/https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u",
     "playerType": 2},
    {"name": "虎牙一起看", "type": 0, "url": "https://sub.ottiptv.cc/huyayqk.m3u",
     "playerType": 2, "timeout": 10, "ua": "okHttp/Mod-1.5.0.0"},
    {"name": "斗鱼一起看", "type": 0, "url": "https://sub.ottiptv.cc/douyuyqk.m3u",
     "playerType": 2, "timeout": 10, "ua": "okHttp/Mod-1.5.0.0"},
    {"name": "YY轮播", "type": 0, "url": "https://sub.ottiptv.cc/yylunbo.m3u",
     "playerType": 2, "timeout": 10, "ua": "okHttp/Mod-1.5.0.0"},
]


# ---------- 基础工具 ----------

def http_get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _now():
    import datetime as _dt
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def jar_classes_and_md5(data):
    """从 jar 的 dex 字节里提取 csp_ 类名集合与 md5"""
    names = set()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if not n.endswith(".dex"):
                continue
            dex = z.read(n)
            for m in re.finditer(rb"Lcom/github/catvod/spider/([^;]+);", dex):
                cls = m.group(1).decode("utf-8", "ignore")
                if "$" in cls:
                    cls = cls.split("$")[0]
                names.add(cls)
    return names, hashlib.md5(data).hexdigest()


def load_first_working_jar(candidates, want_md5=None):
    last = None
    for cand in candidates:
        url = cand.split(";md5;")[0]
        try:
            data = http_get(url)
            classes, md5 = jar_classes_and_md5(data)
            if want_md5 and md5 != want_md5:
                last = f"{url} md5 不匹配（{md5}）"
                continue
            return classes, url, md5
        except Exception as e:
            last = f"{url} 取不到（{e}）"
    raise SystemExit(f"❌ 自有 jar 全部候选不可用：{last}")


def is_drive_api(api):
    cls = str(api or "")
    return "Pan" in cls or "Drive" in cls


def name_tokens(name):
    """站名 → 品牌词：'💓虎斑┃4K💓' → ['虎斑']"""
    raw = (name or "").replace("\u200d", "").replace("\ufe0f", "").strip()
    head = re.split(r"[┃|•·\u2022]", raw)[0]
    head = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", head).lower()
    return [head] if head else []


def is_protected(site):
    """主流线路：名字带 4K 或品牌词在保护名单"""
    if "4k" in (str(site.get("name", "")) + str(site.get("key", ""))).lower():
        return True
    return any(t in PROTECTED_BRANDS for t in name_tokens(site.get("name", "")))


# ---------- 存活探测 ----------

def extract_probe_urls(site):
    """从站点定义里挖出所有可探测地址（ext.site 数组优先，其次 ext 里的 http 串）"""
    urls = []
    ext = site.get("ext")
    if isinstance(ext, dict):
        for v in ext.get("site") or []:
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
        for v in ext.values():
            if isinstance(v, str) and v.startswith("http") and v not in urls:
                urls.append(v)
    elif isinstance(ext, str) and ext.startswith("http"):
        urls.append(ext)
    api = str(site.get("api") or "")
    if api.startswith("http"):
        urls.append(api)
    # drpy2 的 ext 是 js 链接，那是爬虫不是站点本体，不参与探测
    return [u for u in urls if not u.rstrip("/").endswith((".js", ".json"))]


def probe_url_alive(url, timeout=PROBE_TIMEOUT):
    """域名活着就算活（403/405/404 说明服务在），连接失败/超时才叫死"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


def probe_sites(sites):
    """并发探测。返回 (key -> 活地址或 None, 可探测站数)

    一个站有多个候选域名时，返回第一个能连上的那个（探测本身就在做换域名）。
    """
    from concurrent.futures import ThreadPoolExecutor

    items = []
    for s in sites:
        if s.get("_self"):
            continue
        urls = extract_probe_urls(s)
        if urls:
            items.append((s.get("key"), urls))
    if not items:
        return {}, 0

    def work(pair):
        key, urls = pair
        for u in urls:
            if probe_url_alive(u):
                return key, u
        return key, None

    results = {}
    with ThreadPoolExecutor(max_workers=PROBE_WORKERS) as ex:
        for key, url in ex.map(work, items):
            results[key] = url
    return results, len(items)


def apply_probe_results(sites, probe_result):
    """探测结果落库：活→清零并切到活域名；全死→计数；连续 3 天→删/停用

    返回 (删除列表, 停用列表, 复活列表, 换域名列表)
    """
    removed, suspended, revived, switched = [], [], [], []
    for s in sites[:]:
        key = s.get("key")
        if s.get("_self"):
            continue  # 自己的站（js 爬虫）不参与自动删改
        if key not in probe_result:
            continue  # 无可探测地址（token 型网盘站），只能靠 jar 类完整性
        live_url = probe_result[key]
        if live_url:
            if s.get("_fails"):
                s["_fails"] = 0
            # 切到活域名：ext.site 顺序里把它提到第一个，下次直接用
            ext = s.get("ext")
            if isinstance(ext, dict) and isinstance(ext.get("site"), list):
                old = list(ext["site"])
                if old and old[0] != live_url and live_url in old:
                    ext["site"] = [live_url] + [u for u in old if u != live_url]
                    switched.append((key, live_url))
            if s.get("_disabled") and s.get("_dead_by") == "probe":
                s["_disabled"] = False
                s["_dead_by"] = None
                revived.append(key)
            continue

        fails = int(s.get("_fails") or 0) + 1
        s["_fails"] = fails
        s["_last_fail"] = _now()[:10]
        if fails >= PROBE_DELETE_LIMIT and not is_protected(s):
            sites.remove(s)
            removed.append((key, s.get("name", "")))
            continue
        if fails >= PROBE_FAIL_LIMIT:
            if not s.get("_disabled"):
                s["_disabled"] = True
                s["_dead_by"] = "probe"
                suspended.append((key, s.get("name", "")))
    return removed, suspended, revived, switched


# ---------- 库读写 ----------

def load_lib(path=None):
    path = path or LIB_FILE
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        xs = d.get("xs") or {}
        if not isinstance(xs.get("sites"), list) or not xs["sites"]:
            return None
        return d
    except Exception as e:
        print(f"   ⚠ 自有库读取失败（{e}）")
        return None


# ---------- 组装 ----------

def check_classes(sites, jar_classes):
    """jar 类缺失 → 停用留档；类回来了 → 恢复

    停用分两种原因（_dead_by）：
      * noclass —— jar 里没有这个类（自己 jar 更新时可能出现）
      * probe   —— 连续探测失败
    两者各自复活，不能互相覆盖，否则一波操作会把刚停的死站又放出来。
    """
    disabled, revived = [], []
    for s in sites:
        if s.get("_self"):
            continue
        api = str(s.get("api") or "")
        if not api.startswith("csp_"):
            continue
        missing = api[4:] not in jar_classes
        if missing and not s.get("_disabled"):
            s["_disabled"] = True
            s["_dead_by"] = "noclass"
            disabled.append((s.get("key"), api))
        elif not missing and s.get("_disabled") and s.get("_dead_by") == "noclass":
            s["_disabled"] = False
            s["_dead_by"] = None
            revived.append(s.get("key"))
    return disabled, revived


def inject_own_sites(sites):
    """自有采集站并入库：已在库则刷新定义，不在则追加"""
    index = {s.get("key"): i for i, s in enumerate(sites)}
    for own in OWN_CJ_SITES:
        if own["key"] in index:
            sites[index[own["key"]]].update(dict(own))
        else:
            sites.append(dict(own))
    return sites


def unify_config(sites):
    """统一配置中心：只留一个 csp_Config，网盘类统一开启搜索"""
    out = [s for s in sites if s.get("api") not in UNIFIED_DROP_APIS]
    if not any(s.get("api") == CONFIG_CENTER_API for s in out):
        out.insert(0, {
            "key": "配置中心", "name": "配置 • 中心", "type": 3,
            "api": CONFIG_CENTER_API, "searchable": 0, "changeable": 0, "indexs": 0,
            "style": {"type": "rect", "ratio": 1.618}, "_self": True,
        })
    for s in out:
        api = str(s.get("api") or "")
        if api in NO_SEARCH_APIS:
            s["searchable"] = 0
        elif is_drive_api(api):
            s["searchable"] = 1
    return out


def strip_internal(site):
    return {k: v for k, v in site.items() if not str(k).startswith("_")}


# ---------- 主流程 ----------

def main(out_path="tvbox.json"):
    print("→ 解析自有合并 jar…")
    local_jar = os.environ.get("QF_JAR_LOCAL")
    if local_jar and os.path.exists(local_jar):
        with open(local_jar, "rb") as f:
            data = f.read()
        jar_classes, jar_md5 = jar_classes_and_md5(data)
        jar_url = QF_JAR_URLS[0]
    else:
        jar_classes, jar_url, jar_md5 = load_first_working_jar(
            [f"{u};md5;{QF_JAR_MD5}" for u in QF_JAR_URLS], want_md5=QF_JAR_MD5)
    jar_line = f"{jar_url};md5;{jar_md5}"
    print(f"   {jar_url.split('/')[-1]} · {len(jar_classes)} 类 · md5 {jar_md5[:8]}")

    lib = load_lib()
    if not lib:
        raise SystemExit("❌ 找不到自有线路库 own_sites.json，无法生成（库是唯一真相）")
    xs_lib = lib.get("xs") or {}
    sites = [dict(s) for s in xs_lib.get("sites") or []]
    print(f"→ 自有库：{len(sites)} 站")

    # ---- jar 类完整性 ----
    disabled, revived_cls = check_classes(sites, jar_classes)
    if disabled:
        print(f"   ⏸ jar 缺类停用 {len(disabled)} 站")
    if revived_cls:
        print(f"   ▶ 类恢复 {len(revived_cls)} 站")

    # ---- 存活探测 ----
    removed = suspended = revived = switched = []
    if os.environ.get("QF_SKIP_PROBE"):
        print("→ 跳过存活探测（QF_SKIP_PROBE）")
    else:
        print("→ 逐站存活探测…")
        probe_result, probeable = probe_sites(sites)
        dead_now = sum(1 for v in probe_result.values() if not v)
        alive_rate = (probeable - dead_now) / probeable if probeable else 1.0
        print(f"   可探测 {probeable} 站 · 本轮连不上 {dead_now} 站（存活率 {alive_rate:.0%}）")
        if probeable >= PROBE_MIN_SAMPLE and alive_rate < PROBE_MIN_ALIVE_RATE:
            print(f"   ⚠ 存活率低于 {PROBE_MIN_ALIVE_RATE:.0%}，判定本轮网络异常，探测结果作废（不计数不删除）")
        else:
            removed, suspended, revived, switched = apply_probe_results(sites, probe_result)
        if switched:
            print(f"   🔄 自动切域名 {len(switched)} 站："
                  + "、".join(f"{k}" for k, _ in switched[:8]))
        if revived:
            print(f"   ▶ 恢复上线 {len(revived)} 站：" + "、".join(revived[:8]))
        if suspended:
            print(f"   ⏸ 主流线路停用留档 {len(suspended)} 站（连续 {PROBE_FAIL_LIMIT} 天失效）："
                  + "、".join(k for k, _ in suspended[:8]))
        if removed:
            print(f"   ➖ 删除 {len(removed)} 站（连续 {PROBE_FAIL_LIMIT} 天失效）："
                  + "、".join(k for k, _ in removed[:8]))

    sites = inject_own_sites(sites)
    sites = unify_config(sites)

    live = [s for s in sites if not s.get("_disabled")]
    if len(live) < MIN_SITES:
        raise SystemExit(f"❌ 只解析出 {len(live)} 个可用站点（低于 {MIN_SITES}），保留原文件不动")

    out_sites = []
    for s in live:
        c = strip_internal(s)
        c["jar"] = jar_line
        out_sites.append(c)

    keys = [s["key"] for s in out_sites]
    assert len(keys) == len(set(keys)), "存在重复 key"

    lives = [l for l in (xs_lib.get("lives") or []) if l.get("url")] or DEFAULT_LIVES
    out = {
        "spider": jar_line,
        "wallpaper": xs_lib.get("wallpaper"),
        "logo": xs_lib.get("logo"),
        "danmaku": xs_lib.get("danmaku"),
        "sites": out_sites,
        "lives": lives,
        "parses": xs_lib.get("parses") or [],
        "rules": xs_lib.get("rules") or [],
        "hosts": xs_lib.get("hosts") or [],
        "doh": xs_lib.get("doh") or [],
        "flags": xs_lib.get("flags") or [],
        "ads": xs_lib.get("ads") or [],
    }

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=1))

    tpl = json.loads(json.dumps(out, ensure_ascii=False))
    tpl["spider"] = "LOCALJAR"
    for s in tpl["sites"]:
        s["jar"] = "LOCALJAR"
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(out_path)) or ".", "tvbox_local.json")
    with open(tpl_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(tpl, ensure_ascii=False, indent=1))

    # ---- 写回库 ----
    lib_path = os.path.join(os.path.dirname(os.path.abspath(out_path)) or ".", LIB_FILE)
    lib_out = {
        "_meta": {
            "updated_at": _now(),
            "sites": len(sites),
            "live": len(live),
            "note": "自有线路库（唯一真相）：每天探测存活，活域名自动切换，连续失效自动清理",
        },
        "xs": {
            "wallpaper": out.get("wallpaper"),
            "logo": out.get("logo"),
            "danmaku": out.get("danmaku"),
            "lives": lives,
            "parses": out.get("parses") or [],
            "rules": out.get("rules") or [],
            "hosts": out.get("hosts") or [],
            "doh": out.get("doh") or [],
            "flags": out.get("flags") or [],
            "ads": out.get("ads") or [],
            "sites": sites,
        },
    }
    with open(lib_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lib_out, f, ensure_ascii=False, indent=1)

    size = os.path.getsize(out_path)
    digest = hashlib.md5(open(out_path, "rb").read()).hexdigest()
    print(f"✅ 完成：{len(live)} 站（库 {len(sites)}，停用 {len(sites) - len(live)}）"
          f" / {size} B / md5 {digest}")
    failing = [(s.get("key"), s.get("_fails")) for s in sites if s.get("_fails")]
    if failing:
        print(f"   失败计数中 {len(failing)} 站：" + "、".join(f"{k}×{n}" for k, n in failing[:10]))
    cfg_n = sum(1 for s in out_sites if s.get("api") == CONFIG_CENTER_API)
    print(f"   配置中心 {cfg_n} 个 · 网盘类 "
          f"{sum(1 for s in out_sites if is_drive_api(str(s.get('api') or '')))} 个（均开启搜索）")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tvbox.json")