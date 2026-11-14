#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秋风影视 · 上游线路同步器（只取潇洒）

只从潇洒一条上游取最新配置，写出 tvbox.json：
  潇洒  https://9877.kstore.space/sun.json   （AES 加密，需解密）

规则：
  * 全局 spider / 每站点 jar 一律指向【自有固定 jar】，不再信任上游 jar 地址
  * 自有 jar 优先用仓库 jar/qf_spider.jar（gh-proxy 包装），失败再退备用地址
  * 站点声明的 csp_ 类若在 jar 里不存在，剔除并记录
  * 配置中心、各云盘等入口站不参与搜索（searchable=0）
  * 站点 key / name 命中关键词屏蔽表的直接剔除（BLOCKED_KEYWORDS）
  * lives 上游是空壳，沿用线上已有的直播源（DEFAULT_LIVES 兜底）
  * 上游 403/404、jar 全挂、站点数不足时【不写文件】，保留上一次可用配置

饭太硬的站点（带 .so 加壳 jar）不再合并，避免搜索时加载失败。
"""

import base64
import hashlib
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

XIAOSA_URL = "https://9877.kstore.space/sun.json"
UA = "okhttp/3.14.9"
TIMEOUT = 60

# ---- 自有固定 jar（上游 jar 失效不再影响我们）----
QF_JAR_MD5 = "cbe016eb3cb002ae62058604843f5106"
QF_JAR_URLS = [
    "https://aka.doubaocdn.com/s/mQEn4oI1UG",
    "https://gh-proxy.com/https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/jar/qf_spider.jar",
    "https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/jar/qf_spider.jar",
]

# 这些站点是入口/配置页，不该参与搜索
NO_SEARCH_APIS = {"csp_Config", "csp_MyDriveGuard"}


def is_drive_api(api):
    """网盘 / 云盘 / 盘搜类站点：除配置中心与「我的云盘」外，一律参与搜索"""
    if not api or not api.startswith("csp_"):
        return False
    if api in NO_SEARCH_APIS:
        return False
    cls = api[4:]
    return "Pan" in cls or "Drive" in cls

# 关键词屏蔽表：站点 key / name 命中即剔除（家长向 / 非影视类站点不要）
BLOCKED_KEYWORDS = [
    "新片", "预告", "磁力", "荐片", "体育", "呦呦", "蜻蜓", "听书", "戏曲",
    "儿童", "音乐", "哔哩", "课堂", "教育", "教学", "养生", "动漫", "看球",
    "直播", "小说", "弹幕",
]


def is_blocked(site):
    """站点 key / name 命中屏蔽词则返回命中的那个词"""
    text = f"{site.get('key', '')} {site.get('name', '')}".lower()
    for kw in BLOCKED_KEYWORDS:
        if kw.lower() in text:
            return kw
    return None

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


def aes_cbc_decrypt(key, data):
    """AES-CBC 解密（key 与 IV 相同）。优先用 pycryptodome，
    没有该包时退回系统 openssl，避免因缺依赖直接失败。"""
    try:
        from Cryptodome.Cipher import AES
        return AES.new(key, AES.MODE_CBC, key).decrypt(data)
    except ImportError:
        pass
    try:
        from Crypto.Cipher import AES  # 老 pycrypto 命名
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


def http_get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def decrypt_xiaosa(raw):
    """潇洒配置：整份是十六进制文本。
    结构 = "$#<13位密钥>#$" + 密文hex + 尾部重复的13位密钥(26个hex字符)
    密钥右补 "0" 到 16 位，AES/CBC/PKCS7，key 与 IV 相同。
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
    """spider 形如 https://....png;md5;xxxx → (url, md5)"""
    parts = spider.split(";md5;")
    url = parts[0]
    digest = parts[1] if len(parts) > 1 else None
    return url, digest


def load_jar_classes(spider):
    """下载 jar 并校验 md5，返回 (类名集合, jar地址, jar md5)"""
    url, digest = split_spider(spider)
    data = http_get(url)
    jar_md5 = hashlib.md5(data).hexdigest()
    if digest and digest != jar_md5:
        raise ValueError(f"jar md5 不符：声明 {digest}，实际 {jar_md5}")
    names = set()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if not n.endswith(".dex"):
                continue
            dex = z.read(n)
            for m in re.finditer(rb"Lcom/github/catvod/spider/([^;]+);", dex):
                names.add(m.group(1).decode("utf-8", "ignore"))
    return names, url, jar_md5


def load_first_working_jar(candidates):
    """按顺序尝试候选 jar，返回第一个可用的 (类名集合, url, md5)"""
    errors = []
    for spider in candidates:
        try:
            names, url, md5 = load_jar_classes(spider)
            if names:
                return names, url, md5
            errors.append(f"{spider.split(';md5;')[0]} → jar 内没有 csp_ 类")
        except Exception as e:
            errors.append(f"{spider.split(';md5;')[0]} → {e}")
    raise SystemExit("❌ 所有 jar 候选都不可用，保留原文件：\n   " + "\n   ".join(errors))


def build(xs, xs_classes, old_lives, jar_line):
    sites = []
    dropped = []
    blocked = []
    opened = []
    for s in xs["sites"]:
        site = dict(s)
        kw = is_blocked(site)
        if kw:
            blocked.append((site.get("key"), kw))
            continue
        if site.get("api", "").startswith("csp_"):
            cls = site["api"][4:]
            if cls not in xs_classes:
                dropped.append((site.get("key"), site["api"]))
                continue
        if site.get("api") in NO_SEARCH_APIS:
            site["searchable"] = 0
        elif is_drive_api(site.get("api")):
            if site.get("searchable") != 1:
                site["searchable"] = 1
                opened.append(site.get("key"))
        site["jar"] = jar_line
        sites.append(site)

    lives = [l for l in (xs.get("lives") or []) if l.get("url")] or old_lives or DEFAULT_LIVES

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
    return out, dropped, blocked, opened


def main(out_path="tvbox.json"):
    print("→ 解析自有 jar…")
    candidates = [f"{u};md5;{QF_JAR_MD5}" for u in QF_JAR_URLS]
    xs_classes, jar_url, jar_md5 = load_first_working_jar(candidates)
    jar_line = f"{jar_url};md5;{jar_md5}"
    print(f"   自有 jar 来自 {jar_url} · {len(xs_classes)} 类 · md5={jar_md5}")

    print("→ 拉取潇洒配置…")
    try:
        xs = decrypt_xiaosa(http_get(XIAOSA_URL))
    except Exception as e:
        raise SystemExit(f"❌ 上游潇洒配置取不到（{e}），保留原文件不覆盖")
    print(f"   潇洒站点 {len(xs['sites'])}")

    old_lives, old_keys = [], set()
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                old = json.load(f)
            old_lives = [l for l in (old.get("lives") or []) if l.get("url")]
            old_keys = {s["key"] for s in old.get("sites", [])}
        except Exception:
            pass

    out, dropped, blocked, opened = build(xs, xs_classes, old_lives, jar_line)

    if len(out["sites"]) < MIN_SITES:
        raise SystemExit(f"❌ 上游只解析出 {len(out['sites'])} 站（低于 {MIN_SITES}），疑似上游异常，保留原文件")

    keys = [s["key"] for s in out["sites"]]
    assert len(keys) == len(set(keys)), "存在重复 key"

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=1))

    size = os.path.getsize(out_path)
    digest = hashlib.md5(open(out_path, "rb").read()).hexdigest()
    print(f"✅ 同步完成：{len(out['sites'])} 站点 / {size} B / md5 {digest}")
    print(f"   直播源 {len(out['lives'])} 条 · 缺类剔除 {len(dropped)} · 关键词屏蔽 {len(blocked)}")
    print(f"   网盘类开启搜索 {len(opened)} 个：{opened or '无'}")
    for item in blocked:
        print(f"   ⊘ 屏蔽 {item[0]}（命中「{item[1]}」）")
    for item in dropped:
        print(f"   ⚠ 剔除 {item[0]}（{item[1]} 不在 jar 中）")
    if old_keys:
        new_keys = set(keys)
        print(f"   相对上一版：新增 {sorted(new_keys - old_keys) or '无'} / 下线 {sorted(old_keys - new_keys) or '无'}")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tvbox.json")
