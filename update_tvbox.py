#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秋风影视 · 上游线路同步器（潇洒 + 王二小双上游，共用一个合并 jar）

每次运行：
  1. 取潇洒配置（https://9877.kstore.space/sun.json，AES 加密）
  2. 取王二小配置（https://9280.kstore.vip/newwex.json，明文）
  3. 全局 spider 指向【自有合并 jar】= 潇洒 4025 类 + 王二小 145 类打进同一个 dex
     （王二小是 .so 加壳，两套同名 Init/Proxy 已在合成时迁包隔离，单 jar 才不会闪退）

安全阀（关键）：
  * 合并 jar 三个候选全挂 → 【不写文件】，保留上一次可用配置
  * 潇洒上游 403/404、解不出来、或站点数 < 60 → 【不写文件】
  * 王二小配置取不到、或它的 jar 取不到 / md5 与合成时不一致（说明上游换了 jar，
    合并 jar 已不匹配）→ 【自动跳过王二小站点】，只写潇洒那一份，绝不留半坏配置
  * 王二小站点声明的类若不在 jar 里 → 逐条剔除并记录

合并规则：
  * 关键词屏蔽（BLOCKED_KEYWORDS）命中直接剔除
  * 与潇洒 key 重名 / 品牌名重复（热播、爱看、花卷…）/ 已确认同源（原盘=指南、
    逸动=移动、快影=快映）→ 一律保留潇洒那份，王二小的丢弃
  * 需要他自己配置中心授权的网盘站（他的配置中心、我的网盘、115、Emby、AList、
    WebDav、Vod DIY）不并入：网盘配置一律用潇洒的配置中心数据
  * 配置中心 / 我的云盘不参与搜索；其余网盘类 searchable=1
"""

import hashlib
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

XIAOSA_URL = "https://9877.kstore.space/sun.json"
WEX_CFG_URL = "https://9280.kstore.vip/newwex.json"
UA = "okhttp/3.14.9"
TIMEOUT = 60

# ---- 自有【合并 jar】（潇洒 + 王二小，上游 jar 失效都不再影响我们）----
QF_JAR_MD5 = "c58eed36c90d07e45348a2bfc6617a8b"
QF_JAR_URLS = [
    "https://gh-proxy.com/https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/jar/qf_spider_merged.jar",
    "https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/jar/qf_spider_merged.jar",
    "https://aka.doubaocdn.com/s/yBGvoWFdEB",
]

# 王二小的原始加壳 jar：只用来核对 md5/类名，不直接给 App 用
WEX_JAR_MD5 = "541366f5860ceb66e1c3005f5a299afe"
WEX_JAR_URLS = [
    "https://aka.doubaocdn.com/s/G4Tc2uJeLv",
    "http://oss4liview.moji.com/thd_file/2026/11/12/7b563c7039830e7c712e93f27fd2e102.jpg",
]

# ---- 自有线路库（own_sites.json）----
# 2026-11-27 起不再做「每天被上游覆盖」的镜像，改为自有库模式：
#   * 库里的站点就是自己的最终线路，生成 tvbox.json 只读库；
#   * 上游（潇洒/王二小）只当「信号源」：新站加入库、上游下线的站从库删除；
#   * 上游全挂时，库照常出完整配置，不依赖上游。
# 库内站点用 _origin/_self/_since/_disabled 记内部状态，输出时自动剥掉。
SNAPSHOT_FILE = "own_sites.json"
LIB_FILE = SNAPSHOT_FILE
# 兜底/离线时若库超过这个天数没刷新，打印醒目告警（不阻断出片）
SNAPSHOT_MAX_AGE_DAYS = 7

# 这些站点是入口/配置页，不该参与搜索
NO_SEARCH_APIS = {"csp_Config", "csp_MyDriveGuard"}

# 统一配置中心：只保留潇洒的 csp_Config（已在自己合并 jar 里），
# 王二小的两个独立入口（要单独授权、跟潇洒互不相通）直接去掉，
# 所有网盘站共用同一个配置中心扫描/授权。
CONFIG_CENTER_API = "csp_Config"
UNIFIED_DROP_APIS = {"csp_PanConfigGuard", "csp_MyPanGuard"}

# 王二小那边需要「他自己的配置中心」授权的站：统一到潇洒配置中心后全部并入
WEX_NO_MERGE_APIS = set()

# 已确认同源：仅记录说明，不再据此剔除（改由品牌词判重决定去留）
WEX_SAME_SOURCE = {}

# 关键词屏蔽表：站点 key / name 命中即剔除（家长向 / 非影视类站点不要）
# 注意：「玩偶」不在此列（用户 2026-11-27 要求恢复该 4K 线路）
BLOCKED_KEYWORDS = [
    "观影", "盘库", "蜗牛", "新片", "预告", "磁力", "荐片", "体育", "呦呦", "蜻蜓", "听书", "戏曲",
    "儿童", "音乐", "哔哩", "课堂", "教育", "教学", "养生", "动漫", "看球",
    "直播", "小说", "弹幕",
]

# 只精确屏蔽「搜得到、点开没数据」的那几个站点类：
# 观影 / 盘库 / 蜗牛 的详情解析接口已失效；Emby/Emby001 需要自建服务器，没有就是空数据。
# 注意：同族的 快影/剧透/立播/原盘/盘迷/逸动/七味 实测可正常播放，不能整族屏蔽。
BLOCKED_APIS = [
    "csp_AiNewGuanYingGuard",
    "csp_AiNewPianKuGuard",
    "csp_AiNewWoNiu4KGuard",
    "csp_EmbyGuard",
    "csp_EmbyDiyGuard",
]

# 站点数低于这个值就认为上游异常，不覆盖线上文件
MIN_SITES = 60

# 潇洒上游的 lives 是空壳，线上保留这组公开直播源（纯播放列表，不依赖任何 jar）
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

# ---- 自有采集站（不依赖上游、不依赖 jar）----
# 2026-11-27 起非凡/360 改成 drpy2 爬虫（js），在爬虫里把「伦理片」分类和内容整体过滤掉，
# 配置文件只管挂 js；改过滤词只需改仓库 js，不用动电视端。
# 360 的裸域名 360zy.com 已不可用，改用 www.360zy.com。
GH_RAW = "https://gh-proxy.com/https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main"
OWN_CJ_SITES = [
    {
        "key": "ffzy_cj",
        "name": "非凡 • 高清",
        "type": 3,
        "api": "assets://js/lib/drpy2.min.js",
        "searchable": 1,
        "quickSearch": 1,
        "filterable": 0,
        "ext": GH_RAW + "/js/ffzy.js",
        "_self": True,
    },
    {
        "key": "zy360_cj",
        "name": "360 • 高清",
        "type": 3,
        "api": "assets://js/lib/drpy2.min.js",
        "searchable": 1,
        "quickSearch": 1,
        "filterable": 0,
        "ext": GH_RAW + "/js/360zy.js",
        "_self": True,
    },
    {
        # 厂长资源（4kcz.com）：4K 网盘资源站，在线解析播放 + 夸克/百度/迅雷网盘
        "key": "cz4k_js",
        "name": "厂长 • 4K",
        "type": 3,
        "api": "assets://js/lib/drpy2.min.js",
        "searchable": 0,
        "quickSearch": 0,
        "filterable": 0,
        "ext": GH_RAW + "/js/4kcz.js",
        "_self": True,
    },
]


# ---------- 基础工具 ----------

def http_get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def aes_cbc_decrypt(key, data):
    """AES-CBC 解密（key 与 IV 相同）。优先 pycryptodome，退回系统 openssl。"""
    try:
        from Cryptodome.Cipher import AES
        return AES.new(key, AES.MODE_CBC, key).decrypt(data)
    except ImportError:
        pass
    try:
        from Crypto.Cipher import AES
        return AES.new(key, AES.MODE_CBC, key).decrypt(data)
    except ImportError:
        pass
    import subprocess
    import tempfile
    fd, path = tempfile.mkstemp()
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        out = subprocess.run(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-nopad",
             "-K", key.hex(), "-iv", key.hex(), "-in", path],
            capture_output=True, check=True).stdout
        return out
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise SystemExit(f"没有可用的 AES 实现（pycryptodome 未安装且 openssl 不可用）: {e}")
    finally:
        os.unlink(path)


def decrypt_xiaosa(raw):
    """潇洒配置：整份十六进制文本。
    结构 = "$#<13位密钥>#$" + 密文hex + 尾部重复的 13 位密钥(26 hex)。
    """
    h = raw.decode("utf-8", "ignore").strip()
    if len(h) % 2:
        h = h[:-1]
    header = bytes.fromhex(h[:34])
    if header[:2] != b"$#" or header[-2:] != b"#$":
        raise ValueError("潇洒配置格式变了：头部不是 $#...#$")
    key13 = header[2:-2].decode()
    if len(key13) != 13:
        raise ValueError(f"潇洒密钥长度异常: {len(key13)}")
    tail = bytes.fromhex(h[-26:]).decode()
    if tail != key13:
        raise ValueError("潇洒密钥与尾部不匹配")
    cipher = bytes.fromhex(h[34:len(h) - 26])
    key = (key13 + "0" * 16)[:16]
    pt = aes_cbc_decrypt(key.encode(), cipher)
    pad = pt[-1]
    if 1 <= pad <= 16:
        pt = pt[:-pad]
    return json.loads(pt.decode("utf-8", "ignore"))


def split_spider(spider):
    parts = spider.split(";md5;")
    return parts[0], (parts[1] if len(parts) > 1 else None)


def load_snapshot():
    """固化快照（上游兜底）。返回可当 xs 用的 dict；不可用返回 None。"""
    if not os.path.exists(SNAPSHOT_FILE):
        return None
    try:
        with open(SNAPSHOT_FILE, encoding="utf-8") as f:
            snap = json.load(f)
        xs = snap["xs"]
        assert isinstance(xs.get("sites"), list) and len(xs["sites"]) >= MIN_SITES
        return xs
    except Exception as e:
        print(f"   ⚠ 固化快照不可用（{e}）")
        return None


def jar_classes_and_md5(data):
    """从 jar 字节里取 csp_ 类名集合与 md5"""
    names = set()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if not n.endswith(".dex"):
                continue
            dex = z.read(n)
            for m in re.finditer(rb"Lcom/github/catvod/spider/([^;]+);", dex):
                names.add(m.group(1).decode("utf-8", "ignore"))
    return names, hashlib.md5(data).hexdigest()


def load_first_working_jar(candidates, want_md5=None):
    """按顺序试候选 jar；want_md5 给了就要求完全一致。返回 (classes, url, md5)"""
    errors = []
    for spider in candidates:
        try:
            url, _ = split_spider(spider)
            names, md5 = jar_classes_and_md5(http_get(url))
            if want_md5 and md5 != want_md5:
                errors.append(f"{url} → jar 已变（md5 {md5} ≠ {want_md5}）")
                continue
            if names:
                return names, url, md5
            errors.append(f"{url} → jar 内没有 csp_ 类")
        except Exception as e:
            errors.append(f"{spider.split(';md5;')[0]} → {e}")
    raise SystemExit("❌ 所有 jar 候选都不可用，保留原文件：\n   " + "\n   ".join(errors))


# ---------- 站点规则 ----------

def is_blocked(site):
    # 按站点名称匹配关键词（与 APP 端“屏蔽”行为一致）；api 以 .py 结尾的同样剔除
    text = str(site.get("name", "")).lower()
    api = str(site.get("api", "")).lower()
    if api.endswith(".py"):
        return ".py"
    for a in BLOCKED_APIS:
        if api == a.lower():
            return "api:" + a
    for kw in BLOCKED_KEYWORDS:
        if kw.lower() in text:
            return kw
    return None


def is_drive_api(api):
    """网盘 / 云盘 / 盘搜类：除配置中心与「我的云盘」外一律参与搜索"""
    if not api or not api.startswith("csp_"):
        return False
    if api in NO_SEARCH_APIS:
        return False
    cls = api[4:]
    return "Pan" in cls or "Drive" in cls


_TAGS = {"app", "4k", "影视", "视频", "短剧", "云盘", "搜索", "推送",
         "首页", "中心", "网盘", "采集", "秒播", "综合", "diy", "列表", "我的"}
_TAILWORDS = ("机器人", "影视", "短剧", "网盘", "云盘", "搜索", "采集",
              "秒播", "综合", "app", "4k")


def name_tokens(name):
    """把「💓虎斑┃4K💓」这类站名拆成品牌词：['虎斑']

    规则：取「┃」「•」「·」等分隔符之前的第一段，去掉 emoji/符号后小写。
    这样「💥热播┃秒播💥」与「热播 • APP」会撞在同一个品牌词「热播」上。
    """
    raw = (name or "").replace("\u200d", "").replace("\ufe0f", "").strip()
    head = re.split(r"[┃|•·\u2022]", raw)[0]
    head = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", head).lower()
    return [head] if head else []


def brand_index(sites):
    return {t for s in sites for t in name_tokens(s.get("name", ""))}


def merge_wex(xs_sites, wex_sites, wex_classes):
    """把王二小站点去重并入潇洒站点集合。返回 (并入列表, 统计明细)

    注意：xs_sites 要传「潇洒原始站点」而不是过滤后的列表 ——
    jar 缺类时潇洒站会被过滤掉，若拿过滤结果判重，王二小同名站就会顶替进来，
    把库里的站悄悄换成另一家的实现。
    （王二小的两个独立配置中心入口在统一配置中心阶段会被移除，这里不特殊保留）"""
    xs_keys = {s["key"] for s in xs_sites}
    xs_brands = brand_index(xs_sites)
    kept, stat = [], {"blocked": [], "dup": [], "auth": [], "missing": []}
    for s in wex_sites:
        site = {k: v for k, v in s.items() if k != "jar"}
        if site.get("api") in UNIFIED_DROP_APIS:
            continue  # 王二小的独立配置中心入口，不并入（统一用潇洒的配置中心）
        kw = is_blocked(site)
        if kw:
            stat["blocked"].append((site.get("key"), kw))
            continue
        if site["key"] in xs_keys:
            stat["dup"].append((site.get("key"), "与潇洒 key 重名"))
            continue
        same = WEX_SAME_SOURCE.get(site.get("api", ""))
        if same:
            stat["dup"].append((site.get("key"), f"与潇洒「{same}」同源"))
            continue
        hit = [t for t in name_tokens(site.get("name", "")) if t in xs_brands]
        if hit:
            stat["dup"].append((site.get("key"), f"与潇洒品牌重复（{hit[0]}）"))
            continue
        if site.get("api") in WEX_NO_MERGE_APIS:
            stat["auth"].append((site.get("key"), site.get("api")))
            continue
        cls = site.get("api", "")[4:] if site.get("api", "").startswith("csp_") else None
        if cls and wex_classes and cls not in wex_classes:
            stat["missing"].append((site.get("key"), site.get("api")))
            continue
        if is_drive_api(site.get("api")):
            site["searchable"] = 1
        site["_origin"] = "wex"
        kept.append(site)
    return kept, stat


# ---------- 自有线路库 ----------

def _now():
    import datetime as _dt
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def load_lib(path=None):
    """读自有线路库；不存在或损坏返回 None"""
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
        print(f"   ⚠ 自有库读取失败（{e}），按首次导入处理")
        return None


def filter_upstream(cfg, tag, jar_classes):
    """上游配置 → 站点列表（屏蔽词 / 缺类 / 网盘搜索 / 来源标记）"""
    out, dropped, blocked = [], [], []
    for s in cfg.get("sites") or []:
        site = {k: v for k, v in s.items() if k != "jar"}
        if site.get("api") in UNIFIED_DROP_APIS:
            continue  # 王二小的独立配置中心入口，统一配置中心里不要
        kw = is_blocked(site)
        if kw:
            blocked.append((tag, site.get("key"), kw))
            continue
        api = str(site.get("api") or "")
        if api.startswith("csp_") and api[4:] not in jar_classes:
            dropped.append((tag, site.get("key"), api))
            continue
        if is_drive_api(api):
            site["searchable"] = 1
        site["_origin"] = tag
        out.append(site)
    return out, dropped, blocked


def sync_lib(lib_sites, up_sites, xs_keys, wex_keys, xs_ok, wex_ok, jar_classes, today):
    """自有库 + 上游信号 → 新库站点（不修改入参）

    规则：
      * _self 站点（自有采集站/配置中心）不参与上游增删
      * 上游原始配置里已找不到该 key → 从库删除（视为下线）
        （用未过滤的原始 key 判断：jar 缺类不应被当成下线，否则 jar 一更新就丢站）
      * 上游新增 → 加入库（4K 线路插到最前）
      * 两边都有 → 以上游字段为准更新，保留内部标记
      * jar 里缺类 → _disabled=True（不输出、保留档案）；类恢复 → 自动复活
    """
    rep = {"added": [], "removed": [], "updated": [], "disabled": [], "revived": [], "new4k": []}
    up_map = {s["key"]: s for s in up_sites}

    kept = []
    for s in lib_sites:
        key = s.get("key")
        if not key:
            continue
        if s.get("_self"):
            kept.append(dict(s))
            continue
        origin = s.get("_origin") or "xiaosa"
        gone = ((origin == "xiaosa" and xs_ok and key not in xs_keys)
                or (origin == "wex" and wex_ok and key not in wex_keys))
        if gone:
            rep["removed"].append((key, s.get("name", ""), origin))
            continue
        kept.append(dict(s))

    index = {s["key"]: i for i, s in enumerate(kept)}

    for u in up_sites:
        key = u["key"]
        if key in index:
            old = kept[index[key]]
            if old.get("_self"):
                continue
            changed = False
            for k, v in u.items():
                if str(k).startswith("_"):
                    continue
                if old.get(k) != v:
                    changed = True
                old[k] = v
            if changed:
                rep["updated"].append(key)
        else:
            new = dict(u)
            new["_since"] = today
            is4k = "4k" in (str(new.get("name", "")) + key).lower()
            if is4k:
                kept.insert(0, new)
                index = {s["key"]: i for i, s in enumerate(kept)}
                rep["new4k"].append((key, new.get("name", "")))
            else:
                kept.append(new)
                index[key] = len(kept) - 1
            rep["added"].append((key, new.get("name", ""), new.get("_origin")))

    for s in kept:
        api = str(s.get("api") or "")
        missing = api.startswith("csp_") and api[4:] not in jar_classes
        if missing and not s.get("_disabled"):
            s["_disabled"] = True
            rep["disabled"].append((s.get("key"), api))
        elif not missing and s.get("_disabled"):
            s["_disabled"] = False
            rep["revived"].append(s.get("key"))

    return kept, rep


def inject_own_sites(sites):
    """自有站并入库：已在库则刷新定义，不在则追加"""
    index = {s.get("key"): i for i, s in enumerate(sites)}
    for own in OWN_CJ_SITES:
        if own["key"] in index:
            sites[index[own["key"]]].update(dict(own))
        else:
            sites.append(dict(own))
    return sites


def unify_config(sites):
    """统一配置中心：只留一个 csp_Config，所有网盘/云盘站共用

    - 删掉王二小那两个需要单独授权的入口（PanConfigGuard / MyPanGuard）
    - 保证 csp_Config 存在
    - 配置中心不参与搜索，其余网盘类一律开启搜索（统一扫盘）
    """
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


def pick_top(up, lib_xs, key, default=None):
    """顶层配置优先级：上游 → 自有库 → 默认值"""
    if up is not None and up.get(key):
        return up.get(key)
    if lib_xs and lib_xs.get(key):
        return lib_xs.get(key)
    return default


# ---------- 主流程 ----------

def main(out_path="tvbox.json"):
    print("→ 解析自有合并 jar…")
    local_jar = os.environ.get("QF_JAR_LOCAL")
    if local_jar and os.path.exists(local_jar):
        with open(local_jar, "rb") as f:
            data = f.read()
        jar_classes, jar_md5 = jar_classes_and_md5(data)
        jar_url = QF_JAR_URLS[0]
        print(f"   使用本地刚合成的 jar · {len(jar_classes)} 类 · md5={jar_md5}")
    else:
        candidates = [f"{u};md5;{QF_JAR_MD5}" for u in QF_JAR_URLS]
        jar_classes, jar_url, jar_md5 = load_first_working_jar(candidates, want_md5=QF_JAR_MD5)
    jar_line = f"{jar_url};md5;{jar_md5}"
    print(f"   合并 jar 来自 {jar_url} · {len(jar_classes)} 类 · md5={jar_md5}")

    today = _now()[:10]
    lib = load_lib()
    lib_sites = list((lib or {}).get("xs", {}).get("sites") or [])
    print(f"→ 自有线路库：{len(lib_sites)} 站" + ("" if lib else "（首次运行，将从上游全量导入）"))

    # ---- 上游只当信号源：拉不到不影响出片 ----
    xs, xs_ok = None, False
    print("→ 拉取潇洒配置（仅作新增/下线信号）…")
    try:
        xs = decrypt_xiaosa(http_get(XIAOSA_URL))
        xs_ok = True
        print(f"   潇洒站点 {len(xs['sites'])}")
    except Exception as e:
        print(f"   ⚠ 潇洒取不到（{e}），跳过其增删判断")

    wex, wex_ok = None, False
    print("→ 拉取王二小配置（仅作新增/下线信号）…")
    try:
        wex = json.loads(http_get(WEX_CFG_URL).decode("utf-8", "ignore"))
        wex_ok = True
        print(f"   王二小站点 {len(wex.get('sites') or [])}")
    except Exception as e:
        print(f"   ⚠ 王二小取不到（{e}），跳过其增删判断")

    # ---- 上游站点整理 ----
    up_sites, dropped, blocked = [], [], []
    xs_sites = []
    if xs:
        xs_sites, d1, b1 = filter_upstream(xs, "xiaosa", jar_classes)
        up_sites += xs_sites
        dropped += d1
        blocked += b1

    wex_stat = {"dup": [], "blocked": [], "auth": [], "missing": []}
    if wex and wex.get("sites"):
        print("→ 核对王二小 jar（合并前提）…")
        wex_classes = set()
        try:
            wex_classes, wurl, _ = load_first_working_jar(
                [f"{u};md5;{WEX_JAR_MD5}" for u in WEX_JAR_URLS], want_md5=WEX_JAR_MD5)
            print(f"   jar {wurl} · {len(wex_classes)} 类 · md5 一致")
        except SystemExit as e:
            print(f"   ⚠ 王二小 jar 不可用（{e}），本轮到站直接并入库（已在自己 jar 里）")
        wex_kept, wex_stat = merge_wex(xs.get("sites") or [], wex["sites"], wex_classes)
        up_sites += wex_kept

    # ---- 增量同步 ----
    # 下线判断用「上游原始 key」，不吃过滤结果：jar 缺类只停用，不删档
    xs_keys = {s.get("key") for s in (xs or {}).get("sites", [])} if xs_ok else set()
    wex_keys = {s.get("key") for s in (wex or {}).get("sites", [])} if wex_ok else set()
    sites, rep = sync_lib(lib_sites, up_sites, xs_keys, wex_keys, xs_ok, wex_ok, jar_classes, today)
    sites = inject_own_sites(sites)
    sites = unify_config(sites)

    live = [s for s in sites if not s.get("_disabled")]
    if len(live) < MIN_SITES:
        raise SystemExit(f"❌ 只解析出 {len(live)} 个可用站点（低于 {MIN_SITES}），"
                         "疑似上游异常，保留线上文件与自有库不动")

    # ---- 顶层配置：上游 → 库 → 默认 ----
    lib_xs = (lib or {}).get("xs") or {}
    old_lives = []
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                old_lives = [l for l in (json.load(f).get("lives") or []) if l.get("url")]
        except Exception:
            pass

    lives = ([l for l in (pick_top(xs, lib_xs, "lives") or []) if l.get("url")]
             or old_lives or DEFAULT_LIVES)

    out_sites = []
    for s in live:
        c = strip_internal(s)
        c["jar"] = jar_line
        out_sites.append(c)

    out = {
        "spider": jar_line,
        "wallpaper": pick_top(xs, lib_xs, "wallpaper"),
        "logo": pick_top(xs, lib_xs, "logo"),
        "danmaku": pick_top(xs, lib_xs, "danmaku"),
        "sites": out_sites,
        "lives": lives,
        "parses": pick_top(xs, lib_xs, "parses") or [],
        "rules": pick_top(xs, lib_xs, "rules") or [],
        "hosts": pick_top(xs, lib_xs, "hosts") or [],
        "doh": pick_top(xs, lib_xs, "doh") or [],
        "flags": pick_top(xs, lib_xs, "flags") or [],
        "ads": pick_top(xs, lib_xs, "ads") or [],
    }

    keys = [s["key"] for s in out_sites]
    assert len(keys) == len(set(keys)), "存在重复 key"

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=1))

    # ---- 本地包模板 ----
    tpl = json.loads(json.dumps(out, ensure_ascii=False))
    tpl["spider"] = "LOCALJAR"
    for s in tpl["sites"]:
        s["jar"] = "LOCALJAR"
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(out_path)) or ".", "tvbox_local.json")
    with open(tpl_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(tpl, ensure_ascii=False, indent=1))
    print(f"   模板 {os.path.basename(tpl_path)}：{len(tpl['sites'])} 站")

    # ---- 自有库落盘（含内部标记；上游挂了也照常写回，保证库是最新状态） ----
    lib_path = os.path.join(os.path.dirname(os.path.abspath(out_path)) or ".", LIB_FILE)
    lib_out = {
        "_meta": {
            "updated_at": _now(),
            "sites": len(sites),
            "live": len(live),
            "note": "自有线路库：上游只做新增/下线信号，上游挂掉照常出配置",
            "sources": {"xiaosa": xs_ok, "wex": wex_ok},
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
    print(f"✅ 生成完成：{len(live)} 站（库内 {len(sites)}，停用 {len(sites) - len(live)}）"
          f" / {size} B / md5 {digest}")

    if rep["added"]:
        print(f"   ➕ 新增 {len(rep['added'])} 站："
              + "、".join(f"{k}({n})" for k, n, _ in rep["added"][:12]))
    if rep["new4k"]:
        print("   🆕 新 4K 线路：" + "、".join(f"{k}({n})" for k, n in rep["new4k"]))
    if rep["removed"]:
        print(f"   ➖ 下线删除 {len(rep['removed'])} 站："
              + "、".join(f"{k}({o})" for k, _, o in rep["removed"][:12]))
    if rep["disabled"]:
        print(f"   ⏸ 缺类停用 {len(rep['disabled'])} 站："
              + "、".join(f"{k}({a})" for k, a in rep["disabled"][:12]))
    if rep["revived"]:
        print("   ▶ 恢复启用：" + "、".join(rep["revived"][:12]))
    if rep["updated"]:
        print(f"   ↻ 上游字段更新 {len(rep['updated'])} 站")
    if blocked:
        print(f"   ⊘ 关键词屏蔽 {len(blocked)} 站："
              + "、".join(f"{k}({kw})" for _, k, kw in blocked[:10]))
    if dropped:
        print(f"   ⚠ 缺类剔除 {len(dropped)} 站（未入库）")
    if wex_stat["dup"]:
        print(f"   ⊘ 王二小重复 {len(wex_stat['dup'])} 站")

    cfg_n = sum(1 for s in out_sites if s.get("api") == CONFIG_CENTER_API)
    drive_n = sum(1 for s in out_sites if is_drive_api(str(s.get("api") or "")))
    print(f"   配置中心 {cfg_n} 个（统一共用）· 网盘类 {drive_n} 个（均开启搜索）")
    print(f"   来源：潇洒 {'在线' if xs_ok else '离线'} · 王二小 {'在线' if wex_ok else '离线'} · 自有站 {len(OWN_CJ_SITES)} 个")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tvbox.json")