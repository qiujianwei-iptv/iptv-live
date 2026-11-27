// 厂长4K · drpy2 爬虫（https://www.4kcz.com 厂长资源）
// 形态：4K 网盘资源站 + 在线解析播放（v_play 页 iframe 解析，播放走网页嗅探）
// 播放组：在线播放（parse=1 网页解析）/ 网盘（夸克/百度/迅雷分享直接给链接，壳内转存播放）

var rule = {
    title: '厂长4K',
    host: 'https://www.4kcz.com',
    url: '/fyclass/page/fypage',
    searchUrl: '',
    searchable: 0,
    quickSearch: 0,
    filterable: 0,
    headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.4kcz.com/'
    },
    class_name: '最新电影&剧场版&国产剧&美剧&韩剧&番剧&豆瓣Top250',
    class_url: 'zuixindianying&dongmanjuchangban&gcj&meijutt&hanjutv&fanju&dbtop250',
    一级: `js:
let html = request(input);
let d = [];
let cards = html.match(/<li><a href="https:\\/\\/www\\.4kcz\\.com\\/movie\\/\\d+\\.html"[\\s\\S]*?<\\/li>/g) || [];
for (let i = 0; i < cards.length; i++) {
    let c = cards[i];
    let url = (c.match(/href="(https:\\/\\/www\\.4kcz\\.com\\/movie\\/\\d+\\.html)"/) || [])[1] || '';
    let name = (c.match(/alt="([^"]+)"/) || [])[1] || '';
    let pic = (c.match(/data-original="([^"]+)"/) || [])[1] || '';
    let tag = (c.match(/class="furk">([^<]+)<\\/span>/) || [])[1] || '';
    if (url && name) d.push({ title: name.trim(), url: url, img: pic, desc: tag.trim() });
}
setResult(d);`,
    二级: `js:
let html = request(input);
let vod = { vod_id: input };
vod.vod_name = ((html.match(/<h1>([\\s\\S]*?)<\\/h1>/) || [])[1] || '').replace(/<[^>]+>/g, '').trim();
let pic = html.match(/<div class="dyimg[^"]*">[\\s\\S]*?<img[^>]*src="([^"]+)"/);
vod.vod_pic = pic ? pic[1] : '';
let meta = {};
let lis = html.match(/<li>([^：:<]+)[：:]([\\s\\S]*?)<\\/li>/g) || [];
for (let i = 0; i < lis.length; i++) {
    let m = lis[i].match(/<li>([^：:<]+)[：:]([\\s\\S]*?)<\\/li>/);
    if (!m) continue;
    let key = m[1].trim();
    let val = m[2].replace(/<[^>]+>/g, '').trim();
    if (key && val) meta[key] = val;
}
vod.type_name = meta['类型'] || '';
vod.vod_area = meta['地区'] || '';
vod.vod_year = meta['年份'] || '';
vod.vod_remarks = meta['上映'] || '';
vod.vod_content = ((html.match(/<div class="yp_context">([\\s\\S]*?)<\\/div>/) || [])[1] || '').replace(/<[^>]+>/g, ' ').replace(/\\s+/g, ' ').trim();
let plays = [];
let pbtn = html.match(/class="paly_list_btn">([\\s\\S]*?)<\\/div>/);
if (pbtn) {
    let as = pbtn[1].match(/<a[^>]*href="([^"]+)"[^>]*>([^<]*)<\\/a>/g) || [];
    for (let i = 0; i < as.length; i++) {
        let m = as[i].match(/<a[^>]*href="([^"]+)"[^>]*>([^<]*)<\\/a>/);
        if (m) {
            let nm = (m[2] || '在线').replace(/\\s+/g, '').trim();
            plays.push(nm + '$' + m[1].trim());
        }
    }
}
let pans = [];
let dbt = html.match(/id="dwonBT">([\\s\\S]*?)<\\/div>/);
if (dbt) {
    let as = dbt[1].match(/<a[^>]*href="([^"]+)"[^>]*>([\\s\\S]*?)<\\/a>/g) || [];
    for (let i = 0; i < as.length; i++) {
        let m = as[i].match(/<a[^>]*href="([^"]+)"[^>]*>([\\s\\S]*?)<\\/a>/);
        if (!m) continue;
        let href = m[1];
        if (!/(pan\\.quark|pan\\.baidu|pan\\.xunlei|pan\\.alipan|aliyundrive|drive\\.uc|cloud\\.189)/.test(href)) continue;
        let nm = m[2].replace(/<[^>]+>/g, '').replace(/\\s+/g, ' ').trim().replace(/[$#]/g, ' ');
        pans.push((nm || '网盘') + '$' + href);
    }
}
let from = [], urls = [];
if (plays.length) { from.push('在线播放'); urls.push(plays.join('#')); }
if (pans.length) { from.push('网盘'); urls.push(pans.join('#')); }
if (!from.length) { from.push('无资源'); urls.push('暂无资源$' + input); }
vod.vod_play_from = from.join('$$$');
vod.vod_play_url = urls.join('$$$');
VOD = vod;`,
    搜索: '',
    lazy: `js:
if (/v_play/.test(input)) {
    input = { parse: 1, url: input };
} else {
    input = { parse: 0, url: input };
}`
};