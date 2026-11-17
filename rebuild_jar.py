#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秋风影视 · 上游 jar 每周自动合并（增量合并版）

核心思路：**以上一次可用 jar 为底座，只增不删**。
  底座 = 仓库里现有的 jar/qf_spider_merged.jar（已经真机验证能跑）
  往里加：潇洒新 jar 里底座没有的类、王二小 jar 里底座没有的类
  和底座同名的类不覆盖——潇洒的跳过，王二小的迁到 wex. 子包隔离并改写内部引用
  这样上游换 jar、删类，都不会把我们已验证能跑的东西弄丢。

步骤：
  1. 取潇洒 jar（从潇洒配置的 spider 字段，带 md5 校验）
  2. 取王二小加壳 jar（md5 必须等于 541366f…）
  3. 取仓库现有 jar 作底座
  4. 三份都拆 smali，按上面的规则并入
  5. 注入 QfUpdate / QfToast，汇编成 classes.dex，套用底座 jar 的其他资源打包
  6. 回读校验：类数不得少于底座、必须含 QfUpdate、dex 可反编译

安全阀：上游取不到 / md5 不符 / 类数变少 → 不写文件；两个上游 md5 与上次相同 → 直接跳过。

用法：
  python3 rebuild_jar.py --out jar/qf_spider_merged.jar
  env：XS_JAR_URL / WEX_JAR_URL / BASE_JAR_URL 可覆盖（本地联调用）
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
OWN_SMALI = os.path.join(HERE, "jar", "smali")
UA = "okhttp/3.14.9"
TIMEOUT = 90

WEX_JAR_MD5 = "541366f5860ceb66e1c3005f5a299afe"
WEX_JAR_URLS = [
    "https://aka.doubaocdn.com/s/G4Tc2uJeLv",
    "http://oss4liview.moji.com/thd_file/2026/11/12/7b563c7039830e7c712e93f27fd2e102.jpg",
]
BASE_JAR_URLS = [
    "https://gh-proxy.com/https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/jar/qf_spider_merged.jar",
    "https://raw.githubusercontent.com/qiujianwei-iptv/iptv-live/main/jar/qf_spider_merged.jar",
]

RELOC = "wex"


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
        raise SystemExit("命令失败: %s\n%s\n%s" % (" ".join(cmd), p.stdout[-1500:], p.stderr[-1500:]))
    return p.stdout


def baksmali(dex_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    run(["java", "-jar", BAKSMALI_JAR, "d", dex_path, "-o", out_dir])


def assemble(src_dir, out_dex):
    run(["java", "-jar", SMALI_JAR, "a", src_dir, "-o", out_dex, "-a", "15"])


def class_desc(root):
    res = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".smali"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), root)
            res["L" + rel[:-6] + ";"] = rel
    return res


def fetch(url, label):
    try:
        data = http_get(url)
        log("  %s ← %s  %d B md5=%s" % (label, url, len(data), md5(data)))
        return data
    except Exception as e:
        log("  ✗ %s %s → %s" % (label, url, e))
        return None


def fetch_xs_jar():
    override = os.environ.get("XS_JAR_URL")
    if override:
        data = fetch(override, "潇洒 jar")
        if not data:
            raise SystemExit("潇洒 jar（覆盖地址）取不到")
        return data
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
    data = fetch(jar_url, "潇洒 jar")
    if not data:
        raise SystemExit("潇洒 jar 取不到")
    if want and md5(data) != want:
        raise SystemExit("潇洒 jar md5 与配置声明不符：%s ≠ %s" % (md5(data), want))
    return data


def fetch_wex_jar():
    override = os.environ.get("WEX_JAR_URL")
    if override:
        data = fetch(override, "王二小 jar")
        if not data:
            raise SystemExit("王二小 jar（覆盖地址）取不到")
        return data
    for url in WEX_JAR_URLS:
        data = fetch(url, "王二小 jar")
        if data and md5(data) == WEX_JAR_MD5:
            return data
    raise SystemExit("王二小 jar 全部候选不可用或 md5 不符")


def fetch_base_jar():
    override = os.environ.get("BASE_JAR_URL")
    urls = [override] if override else BASE_JAR_URLS
    for url in urls:
        data = fetch(url, "底座 jar")
        if data:
            return data
    raise SystemExit("底座 jar 取不到（为免覆盖成空壳，本次不重建）")


def main():
    out = os.path.join(HERE, "jar", "qf_spider_merged.jar")
    for i, a in enumerate(sys.argv[1:]):
        if a == "--out":
            out = os.path.abspath(sys.argv[i + 2])

    for t in (SMALI_JAR, BAKSMALI_JAR):
        if not os.path.exists(t):
            raise SystemExit("缺少工具 %s" % t)

    log("→ 取上游")
    xs_bytes = fetch_xs_jar()
    wex_bytes = fetch_wex_jar()
    base_bytes = fetch_base_jar()

    xs_md5, wex_md5 = md5(xs_bytes), md5(wex_bytes)
    state_path = os.path.join(HERE, "jar", "upstream_state.json")
    state = {}
    if os.path.exists(state_path):
        try:
            state = json.load(open(state_path, encoding="utf-8"))
        except Exception:
            state = {}
    if state.get("xs_md5") == xs_md5 and state.get("wex_md5") == wex_md5 and os.path.exists(out):
        log("上游两个 jar 都没变化，跳过重建")
        print("MD5=%s" % md5(open(out, "rb").read()))
        return

    work = tempfile.mkdtemp(prefix="qfj_")
    log("→ 拆 smali（工作目录 %s）" % work)
    dirs = {}
    for name, data in (("base", base_bytes), ("xs", xs_bytes), ("wex", wex_bytes)):
        d = os.path.join(work, name + ".dex")
        open(d, "wb").write(read_dex_bytes(data))
        dirs[name] = os.path.join(work, name)
        baksmali(d, dirs[name])
    base_cls = class_desc(dirs["base"])
    xs_cls = class_desc(dirs["xs"])
    wex_cls = class_desc(dirs["wex"])
    log("   底座 %d 类 · 潇洒 %d 类 · 王二小 %d 类" % (len(base_cls), len(xs_cls), len(wex_cls)))

    merged = os.path.join(work, "merged")
    shutil.copytree(dirs["base"], merged)
    have = set(base_cls)

    # ---- 潇洒：底座没有的才加，同名保留底座 ----
    xs_new = xs_ref = 0
    for d, rel in xs_cls.items():
        if d in have:
            xs_ref += 1
            continue
        dst = os.path.join(merged, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(os.path.join(dirs["xs"], rel), dst)
        have.add(d)
        xs_new += 1
    log("   潇洒：新增 %d 类，同名沿用底座 %d 类" % (xs_new, xs_ref))

    # ---- 王二小：底座里已有的（含之前迁过包的）一律沿用，只补真正新增的类 ----
    # 底座里那套已经在真机跑通过，绝不动它；assets 里的 guard / .so 打包时一起带上
    wex_new = wex_keep = 0
    for d, rel in wex_cls.items():
        if d in have:
            wex_keep += 1
            continue
        dst = os.path.join(merged, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(os.path.join(dirs["wex"], rel), dst)
        have.add(d)
        wex_new += 1
    log("   王二小：沿用底座 %d 类，新增 %d 类" % (wex_keep, wex_new))

    own = 0
    if os.path.isdir(OWN_SMALI):
        for f in os.listdir(OWN_SMALI):
            if f.endswith(".smali"):
                shutil.copy(os.path.join(OWN_SMALI, f),
                            os.path.join(merged, "com", "github", "catvod", "spider", f))
                own += 1
    log("   自有类 %d 个已注入" % own)

    log("→ 汇编 + 回读校验")
    merged_dex = os.path.join(work, "classes.dex")
    assemble(merged, merged_dex)
    ck = os.path.join(work, "ck")
    baksmali(merged_dex, ck)
    ck_cls = class_desc(ck)
    if len(ck_cls) < len(base_cls):
        raise SystemExit("❌ 合并后 %d 类少于底座 %d 类，放弃写入" % (len(ck_cls), len(base_cls)))
    if "Lcom/github/catvod/spider/QfUpdate;" not in ck_cls:
        raise SystemExit("❌ 回读校验找不到 QfUpdate")
    log("   通过：%d 类（底座 %d + 潇洒 %d + 王二小 %d + 自有 %d）"
        % (len(ck_cls), len(base_cls), xs_new, wex_new, own))

    # ---- 打包：资源取三方的并集（底座优先，再补潇洒、王二小的 assets）----
    # 王二小真正的站点代码在 assets/wexshinidie.guard + wexguard_v*.so 里，必须带上
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zout:
        seen = set()
        for label, blob in (("base", base_bytes), ("xs", xs_bytes), ("wex", wex_bytes)):
            with zipfile.ZipFile(io.BytesIO(blob)) as zin:
                for item in zin.infolist():
                    name = item.filename
                    if re.match(r"classes\d*\.dex$", name) or name in seen:
                        continue
                    # 签名残留会带来校验问题，一律不进包
                    if re.match(r"META-INF/[^/]+\.(RSA|SF|DSA|EC)$", name, re.I):
                        continue
                    seen.add(name)
                    zout.writestr(item, zin.read(name))
                    log("   资源 %-28s ← %s" % (name, label))
        zi = zipfile.ZipInfo("classes.dex", date_time=(1980, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        zout.writestr(zi, open(merged_dex, "rb").read())

    data = zbuf.getvalue()
    old_md5 = md5(open(out, "rb").read()) if os.path.exists(out) else None
    new_md5 = md5(data)
    if old_md5 == new_md5:
        log("合并 jar 无变化，不写文件")
    else:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(data)
        log("→ 写入 %s  %d B  md5=%s（原 %s）" % (out, len(data), new_md5, old_md5))
        json.dump({"xs_md5": xs_md5, "wex_md5": wex_md5},
                  open(state_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("MD5=%s" % new_md5)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
