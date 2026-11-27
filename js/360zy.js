// 360高清 · drpy2 爬虫（苹果CMS v10 采集接口，from/360azy 线路）
// 作用：直连 360 采集接口，分类/列表/搜索里整体过滤掉「伦理片」（用户 2026-11-27 要求）
// 注意：裸域名 360zy.com 已拒绝连接，改用 www.360zy.com
var rule = {
    title: '360高清',
    host: 'https://www.360zy.com',
    url: '/api.php/provide/vod/from/360azy/?ac=detail&t=fyclass&pg=fypage',
    searchUrl: '/api.php/provide/vod/from/360azy/?wd=**&pg=fypage',
    searchable: 1,
    quickSearch: 1,
    filterable: 0,
    headers: {
        'User-Agent': 'okhttp/3.14.9'
    },
    // 已剔除 5:伦理片
    class_name: '电影&连续剧&综艺&动漫&动作片&喜剧片&爱情片&科幻片&恐怖片&剧情片&战争片&国产剧&香港剧&韩国剧&欧美剧&体育&NBA&惊悚片&家庭篇&古装片&历史片&悬疑片&犯罪片&灾难片&纪录片&短片&动画片&台湾剧&日本剧&海外剧&泰国剧&大陆综艺&港台综艺&日韩综艺&欧美综艺&国产动漫&欧美动漫&日韩动漫&足球&篮球&未分类&西部片&爽文短剧&现代都市&脑洞悬疑&年代穿越&古装仙侠&反转爽剧&女频恋爱&成长逆袭',
    class_url: '1&2&3&4&6&7&8&9&10&11&12&13&14&15&16&17&18&20&21&22&23&24&25&26&27&28&29&30&31&32&33&34&35&36&37&38&39&40&41&42&43&45&46&47&48&49&50&51&52&53',

    一级: `js:
let json = JSON.parse(request(input));
let list = json.list || [];
let bad = /伦理|情色|成人|福利|午夜/;
let d = [];
for (let i = 0; i < list.length; i++) {
    let v = list[i];
    let cls = (v.vod_class || '') + ' ' + (v.type_name || '');
    if (bad.test(cls) || bad.test(v.vod_name || '')) continue;
    d.push({
        title: v.vod_name || '',
        url: '/api.php/provide/vod/from/360azy/?ac=detail&ids=' + v.vod_id,
        img: v.vod_pic || '',
        desc: v.vod_remarks || ''
    });
}
setResult(d);`,

    搜索: `js:
let json = JSON.parse(request(input));
let list = json.list || [];
let bad = /伦理|情色|成人|福利|午夜/;
let d = [];
for (let i = 0; i < list.length; i++) {
    let v = list[i];
    let cls = (v.vod_class || '') + ' ' + (v.type_name || '');
    if (bad.test(cls) || bad.test(v.vod_name || '')) continue;
    d.push({
        title: v.vod_name || '',
        url: '/api.php/provide/vod/from/360azy/?ac=detail&ids=' + v.vod_id,
        img: v.vod_pic || '',
        desc: v.vod_remarks || ''
    });
}
setResult(d);`,

    二级: `js:
let json = JSON.parse(request(input));
let list = json.list || [];
let v = list.length ? list[0] : null;
if (!v) {
    VOD = {
        vod_id: input, vod_name: '解析失败', vod_pic: '',
        vod_play_from: '提示', vod_play_url: '返回重试$' + input
    };
} else {
    VOD = {
        vod_id: v.vod_id,
        vod_name: v.vod_name || '',
        vod_pic: v.vod_pic || '',
        type_name: v.vod_class || v.type_name || '',
        vod_year: v.vod_year || '',
        vod_area: v.vod_area || '',
        vod_remarks: v.vod_remarks || '',
        vod_content: (v.vod_content || '').replace(/<[^>]+>/g, ' ').trim(),
        vod_play_from: v.vod_play_from || '',
        vod_play_url: v.vod_play_url || ''
    };
}`
};