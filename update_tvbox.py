#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秋风影视 · 上游线路合并器

从两条上游取最新配置并合并成一份 tvbox.json：
  1. 潇洒   https://9877.kstore.space/sun.json          （AES 加密，需解密）
  2. 饭太硬 http://www.饭太硬.art/tv                     （配置藏在 JPEG 尾部）

合并规则：
  * 全局 spider 用潇洒的 jar（兜底）
  * 每个站点各自挂自己那条线路的 jar（含 md5 校验位）
  * 与潇洒重名的站点只保留潇洒版
  * 站点声明的 csp_ 类若在它自己的 jar 里不存在，剔除并记录
  * parses / doh / flags / ads / danmaku / wallpaper / logo 用潇洒
  * lives 用饭太硬（潇洒是空壳），rules 两边合并去重
  * 配置中心不参与搜索（searchable=0）；「我的云盘」入口并入配置中心后不再单独保留
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
FAN_URL = "http://www.xn--sss604efuw.cc/tv"
UA = "okhttp/3.14.9"
TIMEOUT = 60

# 这些站点是入口/配置页，不该参与搜索
NO_SEARCH_APIS = {"csp_Config", "csp_MyDriveGuard"}
# 「配置中心」与「我的云盘」保持各自独立入口（用户 2026-11-13 要求恢复合并前的状态）
DROP_ENTRY_APIS = set()

# 站点数低于这个值就认为上游异常，不覆盖线上文件
MIN_SITES = 60

# 这些关键词出现在站点 key 或 name 里就整条屏蔽（不想要的片源类型）
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


def extract_fan(raw):
    """饭太硬配置：返回的是一张 JPEG，EOI(FFD9) 之后挂着 base64 文本。
    解码后跳过 6 字节二进制前缀，去掉行首 // 注释即为明文 JSON。
    """
    if not raw.startswith(b"\xff\xd8"):
        raise ValueError("饭太硬返回的不是 JPEG，可能被防爬页替代")
    idx = raw.rfind(b"\xff\xd9")
    if idx < 0:
        raise ValueError("饭太硬图片里找不到 EOI，无法取配置")
    tail = raw[idx + 2:].decode("utf-8", "ignore").strip()
    payload = base64.b64decode(tail)[6:]
    lines = [ln for ln in payload.decode("utf-8", "ignore").splitlines()
             if not ln.strip().startswith("//")]
    return json.loads("\n".join(lines).strip())


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
    # 这些"jar"其实是 dex（classes.dex 里是 com/github/catvod/spider/XXX 的类描述符）
    names = set()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if not n.endswith(".dex"):
                continue
            dex = z.read(n)
            for m in re.finditer(rb"Lcom/github/catvod/spider/([^;]+);", dex):
                names.add(m.group(1).decode("utf-8", "ignore"))
    return names, url, jar_md5


class JarRegistry:
    """按 jar 地址缓存「类名集合」，并逐个校验配置里声明的 md5。
    站点若自带 jar，就用它自己的；否则用所属线路的兜底 spider。
    """

    def __init__(self):
        self._cache = {}
        self.info = []

    def classes(self, spider):
        if spider not in self._cache:
            names, url, md5 = load_jar_classes(spider)
            self._cache[spider] = names
            self.info.append((spider, url, md5, len(names)))
        return self._cache[spider]


def merge(xs, fan, jars):
    report = {"dropped_missing_class": [], "dropped_duplicate": [],
              "dropped_blocked": [], "dropped_merged": [], "kept_fan": 0}

    xs_jar = xs["spider"]
    fan_jar = fan["spider"]
    xs_keys = {s["key"] for s in xs["sites"]}
    sites = []

    for s in xs["sites"]:
        site = dict(s)
        kw = is_blocked(site)
        if kw:
            report["dropped_blocked"].append((site["key"], kw))
            continue
        if site.get("api") in DROP_ENTRY_APIS:
            report["dropped_merged"].append((site["key"], "潇洒"))
            continue
        jar = site.get("jar") or xs_jar
        if site.get("api", "").startswith("csp_"):
            cls = site["api"][4:]
            if cls not in jars.classes(jar):
                report["dropped_missing_class"].append((site["key"], site["api"], "潇洒"))
                continue
        if site.get("api") in NO_SEARCH_APIS:
            site["searchable"] = 0
        site["jar"] = jar
        sites.append(site)

    for s in fan["sites"]:
        site = dict(s)
        kw = is_blocked(site)
        if kw:
            report["dropped_blocked"].append((site["key"], kw))
            continue
        if site.get("api") in DROP_ENTRY_APIS:
            report["dropped_merged"].append((site["key"], "饭太硬"))
            continue
        if site["key"] in xs_keys:
            report["dropped_duplicate"].append(site["key"])
            continue
        jar = site.get("jar") or fan_jar
        if site.get("api", "").startswith("csp_"):
            cls = site["api"][4:]
            if cls not in jars.classes(jar):
                report["dropped_missing_class"].append((site["key"], site["api"], "饭太硬"))
                continue
        if site.get("api") in NO_SEARCH_APIS:
            site["searchable"] = 0
        site["jar"] = jar
        sites.append(site)
        report["kept_fan"] += 1

    rules = list(xs.get("rules") or [])
    seen = {r.get("name") for r in rules}
    for r in (fan.get("rules") or []):
        if r.get("name") not in seen:
            rules.append(r)
            seen.add(r.get("name"))

    out = {
        "spider": xs_jar,
        "wallpaper": xs.get("wallpaper"),
        "logo": xs.get("logo"),
        "danmaku": xs.get("danmaku"),
        "sites": sites,
        "lives": fan.get("lives") or [],
        "parses": xs.get("parses") or [],
        "rules": rules,
        "hosts": fan.get("hosts") or [],
        "doh": xs.get("doh") or [],
        "flags": xs.get("flags") or [],
        "ads": xs.get("ads") or [],
    }
    return out, report


def main(out_path="tvbox.json"):
    print("→ 拉取潇洒配置…")
    xs = decrypt_xiaosa(http_get(XIAOSA_URL))
    print(f"   潇洒站点 {len(xs['sites'])}")

    print("→ 拉取饭太硬配置…")
    fan = extract_fan(http_get(FAN_URL))
    print(f"   饭太硬站点 {len(fan['sites'])}")

    print("→ 下载并校验全部 jar（含上游站点自带的）…")
    jars = JarRegistry()
    for s in list(xs["sites"]) + list(fan["sites"]):
        spider = s.get("jar")
        if spider:
            jars.classes(spider)
    jars.classes(xs["spider"])
    jars.classes(fan["spider"])
    for spider, url, md5, n in jars.info:
        print(f"   {url.split('/')[-1][:28]:30s} {n:5d} 类 md5={md5}")

    merged, report = merge(xs, fan, jars)

    # 安全闸：站点数异常（上游挂掉/解析走偏）时直接失败，不覆盖线上的好文件
    if len(merged["sites"]) < MIN_SITES:
        raise SystemExit(f"❌ 合并结果只有 {len(merged['sites'])} 站（低于 {MIN_SITES}），疑似上游异常，保留原文件")

    keys = [s["key"] for s in merged["sites"]]
    assert len(keys) == len(set(keys)), "合并后存在重复 key"

    # 与现有文件的差异（便于在提交信息里体现增减）
    old_keys = set()
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                old_keys = {s["key"] for s in json.load(f).get("sites", [])}
        except Exception:
            old_keys = set()

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(merged, ensure_ascii=False, indent=1))

    new_keys = set(keys)
    size = os.path.getsize(out_path)
    digest = hashlib.md5(open(out_path, "rb").read()).hexdigest()
    print(f"✅ 合并完成：{len(merged['sites'])} 站点 / {size} B / md5 {digest}")
    print(f"   潇洒 {len(merged['sites']) - report['kept_fan']} 站 · 饭太硬 {report['kept_fan']} 站 · "
          f"重名跳过 {len(report['dropped_duplicate'])} · 缺类剔除 {len(report['dropped_missing_class'])}")
    if report["dropped_blocked"]:
        print(f"   关键词屏蔽 {len(report['dropped_blocked'])} 站："
              + "、".join(f"{k}({kw})" for k, kw in report["dropped_blocked"]))
    for item in report["dropped_missing_class"]:
        print(f"   ⚠ 剔除 {item[0]}（{item[1]} 不在{item[2]}jar 中）")
    if old_keys:
        added = sorted(new_keys - old_keys)
        removed = sorted(old_keys - new_keys)
        print(f"   相对上一版：新增 {added or '无'} / 下线 {removed or '无'}")
    return merged


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tvbox.json")
