#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秋风影视 · 上游 jar 每周自动合并

做的事情：
  1. 取潇洒 jar（从潇洒配置里的 spider 字段）+ 取王二小加壳 jar
  2. 两个 jar 都拆成 smali
  3. 以潇洒为底座；王二小里「潇洒没见过的类」原样并入，
     与潇洒同名冲突的类（Init/Proxy 这类）整体迁到 wex. 子包隔离，再把内部引用改写过去
  4. 注入我们自己的 QfUpdate / QfToast
  5. 汇编成一个 classes.dex，套用潇洒 jar 的其他资源，产出合并 jar
  6. 回读校验：类数、我们的两个类、dex 可反编译

安全阀：
  · 任何一个上游取不到 → 不写文件，保留现有 jar
  · 合并后类数少于潇洒原先的类数 → 不写文件
  · 回读校验失败 → 不写文件

用法：
  python3 rebuild_jar.py --out jar/qf_spider_merged.jar
  可用环境变量覆盖上游地址做本地联调：
    XS_JAR_URL / WEX_JAR_URL
"""

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "jar", "tools")
SMALI_JAR = os.path.join(TOOLS, "smali.jar")
BAKSMALI_JAR = os.path.join(TOOLS, "baksmali.jar")
OWN_SMALI = os.path.join(HERE, "jar", "smali")   # QfUpdate.smali / QfToast.smali
UA = "okhttp/3.14.9"
TIMEOUT = 90

WEX_JAR_MD5 = "541366f5860ceb66e1c3005f5a299afe"
WEX_JAR_URLS = [
    "https://aka.doubaocdn.com/s/G4Tc2uJeLv",
    "http://oss4liview.moji.com/thd_file/2026/11/12/7b563c7039830e7c712e93f27fd2e102.jpg",
]

RELOC_PREFIX = "Lcom/github/catvod/spider/wex/"


def log(msg):
    print(msg, flush=True)


def http_get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def md5(b):
    return hashlib.md5(b).hexdigest()


def read_dex_bytes(jar_bytes):
    z = zipfile.ZipFile(io.BytesIO(jar_bytes))
    names = [n for n in z.namelist() if re.match(r"classes\d*\.dex$", n)]
    if not names:
        raise SystemExit("jar 里没有 classes.dex")
    if len(names) > 1:
        raise SystemExit("jar 里有多于一个 dex（%s），本次不支持" % ",".join(names))
    return z.read(names[0])


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit("命令失败: %s\n%s\n%s" % (" ".join(cmd), p.stdout[-2000:], p.stderr[-2000:]))
    return p.stdout


def baksmali(dex_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    run(["java", "-jar", BAKSMALI_JAR, "d", dex_path, "-o", out_dir])


def assemble(src_dir, out_dex):
    run(["java", "-jar", SMALI_JAR, "a", src_dir, "-o", out_dex, "-a", "15"])


def class_desc(root):
    """返回 {descriptor: smali 文件相对路径}"""
    res = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".smali"):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, root)
            desc = "L" + rel[:-6] + ";"
            res[desc] = rel
    return res


def sha_jar_ok(url):
    try:
        data = http_get(url)
        return data, md5(data)
    except Exception as e:
        log("  ✗ %s → %s" % (url, e))
        return None, None


def fetch_xs_jar():
    override = os.environ.get("XS_JAR_URL")
    if override:
        data, m = sha_jar_ok(override)
        if not data:
            raise SystemExit("潇洒 jar（覆盖地址）取不到")
        return data, m, override
    # 走 update_tvbox 的潇洒配置解密拿 spider
    sys.path.insert(0, HERE)
    import update_tvbox as u
    raw = u.http_get(u.XIAOSA_URL)
    cfg = u.decrypt_xiaosa(raw)
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    spider = (cfg.get("spider") or "").strip()
    if not spider:
        raise SystemExit("潇洒配置里没有 spider 字段")
    jar_url = spider.split(";md5;")[0]
    want = spider.split(";md5;")[1] if ";md5;" in spider else None
    data, m = sha_jar_ok(jar_url)
    if not data:
        raise SystemExit("潇洒 jar 取不到：%s" % jar_url)
    if want and m != want:
        raise SystemExit("潇洒 jar md5 与配置声明不符：%s ≠ %s" % (m, want))
    return data, m, jar_url


def fetch_wex_jar():
    override = os.environ.get("WEX_JAR_URL")
    if override:
        data, m = sha_jar_ok(override)
        if not data:
            raise SystemExit("王二小 jar（覆盖地址）取不到")
        return data, m, override
    for url in WEX_JAR_URLS:
        data, m = sha_jar_ok(url)
        if data and m == WEX_JAR_MD5:
            return data, m, url
    raise SystemExit("王二小 jar 全部候选不可用或 md5 不符")


def main():
    out = os.path.join(HERE, "jar", "qf_spider_merged.jar")
    for i, a in enumerate(sys.argv[1:]):
        if a == "--out":
            out = os.path.abspath(sys.argv[i + 2])

    for t in (SMALI_JAR, BAKSMALI_JAR):
        if not os.path.exists(t):
            raise SystemExit("缺少工具 %s" % t)

    work = tempfile.mkdtemp(prefix="qfj_")
    log("工作目录 %s" % work)

    state_path = os.path.join(HERE, "jar", "upstream_state.json")
    xs_bytes, xs_md5, xs_url = fetch_xs_jar()
    log("潇洒 jar  %s  md5=%s  %d B" % (xs_url, xs_md5, len(xs_bytes)))
    wex_bytes, wex_md5, wex_url = fetch_wex_jar()
    log("王二小 jar %s  md5=%s  %d B" % (wex_url, wex_md5, len(wex_bytes)))

    state = {}
    if os.path.exists(state_path):
        try:
            state = json.load(open(state_path, encoding="utf-8"))
        except Exception:
            state = {}
    if (state.get("xs_md5") == xs_md5 and state.get("wex_md5") == wex_md5 and os.path.exists(out)):
        log("上游两个 jar 都没变化，跳过重建")
        print("MD5=%s" % md5(open(out, "rb").read()))
        return

    xs_dex = os.path.join(work, "xs.dex")
    wex_dex = os.path.join(work, "wex.dex")
    open(xs_dex, "wb").write(read_dex_bytes(xs_bytes))
    open(wex_dex, "wb").write(read_dex_bytes(wex_bytes))

    xs_dir = os.path.join(work, "xs")
    wex_dir = os.path.join(work, "wex")
    baksmali(xs_dex, xs_dir)
    baksmali(wex_dex, wex_dir)

    xs_cls = class_desc(xs_dir)
    wex_cls = class_desc(wex_dir)
    log("潇洒类数 %d · 王二小类数 %d" % (len(xs_cls), len(wex_cls)))

    merged = os.path.join(work, "merged")
    shutil.copytree(xs_dir, merged)

    clashes = [d for d in wex_cls if d in xs_cls]
    log("同名冲突类 %d 个：%s" % (len(clashes), ", ".join(c.split("/")[-1][:-1] for c in clashes[:12])))

    # 名字迁移映射：冲突类整体挪到 wex. 子包
    rename = {}
    for d in wex_cls:
        if d in xs_cls:
            inner = d[1:-1]
            parts = inner.split("/")
            rename[d] = "L" + "/".join(parts[:-1] + ["wex", parts[-1]]) + ";"

    added = 0
    for d, rel in wex_cls.items():
        src = os.path.join(wex_dir, rel)
        txt = open(src, encoding="utf-8").read()
        newd = rename.get(d, d)
        if rename:
            for old, new in rename.items():
                if old in txt:
                    txt = txt.replace(old, new)
        rel_new = newd[1:-1] + ".smali"
        dst = os.path.join(merged, rel_new)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, "w", encoding="utf-8").write(txt)
        added += 1

    log("并入王二小类 %d 个（其中迁包 %d 个）" % (added, len(rename)))

    # 注入自有类
    own = 0
    if os.path.isdir(OWN_SMALI):
        for f in os.listdir(OWN_SMALI):
            if f.endswith(".smali"):
                shutil.copy(os.path.join(OWN_SMALI, f),
                            os.path.join(merged, "com", "github", "catvod", "spider", f))
                own += 1
    log("注入自有类 %d 个" % own)

    merged_dex = os.path.join(work, "classes.dex")
    assemble(merged, merged_dex)

    # 回读校验
    ck = os.path.join(work, "ck")
    baksmali(merged_dex, ck)
    ck_cls = class_desc(ck)
    got_own = [c for c in ck_cls if c in ("Lcom/github/catvod/spider/QfUpdate;", "Lcom/github/catvod/spider/QfToast;")]
    if len(ck_cls) < len(xs_cls):
        raise SystemExit("❌ 合并后类数 %d 少于潇洒 %d，放弃写入" % (len(ck_cls), len(xs_cls)))
    if "QfUpdate" not in "".join(got_own):
        raise SystemExit("❌ 回读校验找不到 QfUpdate")
    log("回读校验通过：%d 类（潇洒 %d + 王二小 %d + 自有 %d）" % (len(ck_cls), len(xs_cls), added, own))

    # 打包：沿用潇洒 jar 的非 dex 资源
    zbuf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(xs_bytes)) as zin, zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if re.match(r"classes\d*\.dex$", item.filename):
                continue
            zout.writestr(item, zin.read(item.filename))
        zi = zipfile.ZipInfo("classes.dex", date_time=(1980, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        zout.writestr(zi, open(merged_dex, "rb").read())

    data = zbuf.getvalue()
    old_md5 = None
    if os.path.exists(out):
        old_md5 = md5(open(out, "rb").read())
    new_md5 = md5(data)
    if old_md5 == new_md5:
        log("合并 jar 无变化（md5 相同），不写文件")
    else:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(data)
        log("写入 %s  %d B  md5=%s（原 %s）" % (out, len(data), new_md5, old_md5))
    if old_md5 != new_md5:
        json.dump({"xs_md5": xs_md5, "wex_md5": wex_md5},
                  open(state_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("MD5=%s" % new_md5)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
