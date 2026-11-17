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
QF_JAR_MD5 = "1ade76d8a994db1965c3d8d10e570961"
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

# 这些站点是入口/配置页，不该参与搜索
NO_SEARCH_APIS = {"csp_Config", "csp_MyDriveGuard"}

# 王二小自己的两个入口（配置中心 / 我的网盘）：不参与去重，必须常驻，且不参与搜索
WEX_KEEP_KEYS = {"Wexconfig", "MyPan"}

# 王二小那边需要「他自己的配置中心」授权的站：全部并入，两套网盘入口都保留
# （潇洒「配置 • 中心」、王二小「🐮配置┃中心🐮」+「🐮我的┃网盘🐮」互不相通，
#   王二小的网盘站点必须在那两个入口各扫一次授权才可播放）
WEX_NO_MERGE_APIS = set()

# 已确认同源：仅记录说明，不再据此剔除（改由品牌词判重决定去留）
WEX_SAME_SOURCE = {}

# 关键词屏蔽表：站点 key / name 命中即剔除（家长向 / 非影视类站点不要）
BLOCKED_KEYWORDS = [
    "新片", "预告", "磁力", "荐片", "体育", "呦呦", "蜻蜓", "听书", "戏曲",
    "儿童", "音乐", "哔哩", "课堂", "教育", "教学", "养生", "动漫", "看球",
    "直播", "小说", "弹幕",
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
    text = f"{site.get('key', '')} {site.get('name', '')}".lower()
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
    """把王二小站点去重并入潇洒站点集合。返回 (并入列表, 统计明细)"""
    xs_keys = {s["key"] for s in xs_sites}
    xs_brands = brand_index(xs_sites)
    kept, stat = [], {"blocked": [], "dup": [], "auth": [], "missing": []}
    for s in wex_sites:
        site = {k: v for k, v in s.items() if k != "jar"}
        if site.get("key") in WEX_KEEP_KEYS:
            site["searchable"] = 0
            kept.append(site)
            continue
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
        kept.append(site)
    return kept, stat


# ---------- 主流程 ----------

def main(out_path="tvbox.json"):
    print("→ 解析自有合并 jar…")
    candidates = [f"{u};md5;{QF_JAR_MD5}" for u in QF_JAR_URLS]
    jar_classes, jar_url, jar_md5 = load_first_working_jar(candidates, want_md5=QF_JAR_MD5)
    jar_line = f"{jar_url};md5;{jar_md5}"
    print(f"   合并 jar 来自 {jar_url} · {len(jar_classes)} 类 · md5={jar_md5}")

    print("→ 拉取潇洒配置…")
    try:
        xs = decrypt_xiaosa(http_get(XIAOSA_URL))
    except Exception as e:
        raise SystemExit(f"❌ 上游潇洒配置取不到（{e}），保留原文件不覆盖")
    print(f"   潇洒站点 {len(xs['sites'])}")

    # ---- 王二小：任何一环不对就整段跳过，绝不写半坏配置 ----
    wex_sites, wex_classes, wex_note = [], set(), "未启用"
    print("→ 拉取王二小配置…")
    try:
        wex = json.loads(http_get(WEX_CFG_URL).decode("utf-8", "ignore"))
        wex_sites = wex.get("sites", [])
        print(f"   王二小站点 {len(wex_sites)}")
    except Exception as e:
        wex_sites = []
        wex_note = f"配置取不到（{e}），跳过王二小"
        print(f"   ⚠ {wex_note}")

    if wex_sites:
        print("→ 核对王二小 jar（合成前提）…")
        try:
            wex_classes, wurl, wmd5 = load_first_working_jar(
                [f"{u};md5;{WEX_JAR_MD5}" for u in WEX_JAR_URLS], want_md5=WEX_JAR_MD5)
            print(f"   jar {wurl} · {len(wex_classes)} 类 · md5 一致")
            wex_note = "已合并"
        except SystemExit as e:
            wex_sites = []
            wex_classes = set()
            wex_note = "王二小 jar 不可用或已更新（合并 jar 不匹配），跳过王二小"
            print(f"   ⚠ {wex_note}\n      {e}")

    old_lives = []
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                old = json.load(f)
            old_lives = [l for l in (old.get("lives") or []) if l.get("url")]
        except Exception:
            pass

    # ---- 潇洒侧：沿用原有过滤 ----
    sites, dropped, blocked, opened = [], [], [], []
    for s in xs["sites"]:
        site = dict(s)
        kw = is_blocked(site)
        if kw:
            blocked.append((site.get("key"), kw))
            continue
        if site.get("api", "").startswith("csp_"):
            cls = site["api"][4:]
            if cls not in jar_classes:
                dropped.append((site.get("key"), site["api"]))
                continue
        if site.get("api") in NO_SEARCH_APIS:
            site["searchable"] = 0
        elif is_drive_api(site.get("api")):
            if site.get("searchable") != 1:
                site["searchable"] = 1
                opened.append(site.get("key"))
        sites.append(site)

    print("→ 合并王二小站点…")
    kept, wstat = merge_wex(sites, wex_sites, wex_classes) if wex_sites else ([], {"blocked": [], "dup": [], "auth": [], "missing": []})
    sites += kept

    # ---- 秋风影视自有「线路包更新」入口（类 csp_QfUpdate 在合并 jar 内，打开即检查）----
    if "QfUpdate" in jar_classes:
        sites.append({
            "key": "QfUpdate",
            "name": "🔄 线路包更新",
            "type": 3,
            "api": "csp_QfUpdate",
            "searchable": 0,
        })
    print(f"   并入 {len(kept)} 条 · 重复剔除 {len(wstat['dup'])} · 需他自己网盘授权剔除 "
          f"{len(wstat['auth'])} · 关键词剔除 {len(wstat['blocked'])} · 缺类剔除 {len(wstat['missing'])}")

    lives = [l for l in (xs.get("lives") or []) if l.get("url")] or old_lives or DEFAULT_LIVES

    # ---- 站点改名（首页第一站统一叫「秋风线路」）----
    for s in sites:
        if s.get("api") == "csp_Douban":
            s["name"] = "秋风线路"

    out = {
        "spider": jar_line,
        "wallpaper": xs.get("wallpaper"),
        "logo": xs.get("logo"),
        "danmaku": xs.get("danmaku"),
        "sites": sites,
        "lives": lives,
        "parses": xs.get("parses") or [],
        "rules": xs.get("rules") or [],
        "hosts": xs.get("hosts") or [],
        "doh": xs.get("doh") or [],
        "flags": xs.get("flags") or [],
        "ads": xs.get("ads") or [],
    }

    if len([s for s in sites if s.get("key") not in {k["key"] for k in kept}]) < MIN_SITES:
        raise SystemExit(f"❌ 潇洒侧只解析出 {len(sites) - len(kept)} 站（低于 {MIN_SITES}），"
                         "疑似上游异常，保留原文件")

    keys = [s["key"] for s in sites]
    assert len(keys) == len(set(keys)), "存在重复 key"
    for s in sites:
        s["jar"] = jar_line

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=1))

    # ---- 同步产出「本地包模板」：jar 全部写成 LOCALJAR 占位 ----
    tpl = json.loads(json.dumps(out, ensure_ascii=False))
    tpl["spider"] = "LOCALJAR"
    for s in tpl["sites"]:
        s["jar"] = "LOCALJAR"
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(out_path)) or ".", "tvbox_local.json")
    with open(tpl_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(tpl, ensure_ascii=False, indent=1))
    print(f"   模板 {os.path.basename(tpl_path)}：{len(tpl['sites'])} 站 / "
          f"{os.path.getsize(tpl_path)} B / LOCALJAR {sum(1 for s in tpl['sites'] if s['jar']=='LOCALJAR')+1} 处")

    size = os.path.getsize(out_path)
    digest = hashlib.md5(open(out_path, "rb").read()).hexdigest()
    print(f"✅ 同步完成：{len(sites)} 站点 / {size} B / md5 {digest}")
    print(f"   王二小：{wex_note}")
    print(f"   直播源 {len(lives)} 条 · 潇洒缺类剔除 {len(dropped)} · 潇洒关键词屏蔽 {len(blocked)}")
    print(f"   网盘类开启搜索 {len(opened)} 个：{opened or '无'}")
    for item in blocked:
        print(f"   ⊘ 屏蔽 {item[0]}（命中「{item[1]}」）")
    for item in dropped:
        print(f"   ⚠ 剔除 {item[0]}（{item[1]} 不在 jar 中）")
    for name, rows in (("重复", wstat["dup"]), ("需自有网盘授权", wstat["auth"]),
                       ("关键词", wstat["blocked"]), ("缺类", wstat["missing"])):
        for row in rows:
            print(f"   ⊘ 王二小 {name}剔除 {row[0]}（{row[1]}）")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tvbox.json")
