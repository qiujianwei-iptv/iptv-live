// 非凡高清 · drpy2 爬虫（苹果CMS v10 采集接口）
// 伦理片屏蔽：三层拦截（用户 2026-11-27 要求）
//   1) 分类表里没有「伦理片」，也不给对应 type_id
//   2) 一级/搜索：按 type_name、vod_class、片名命中敏感词一律丢弃
//   3) 详情页：即便通过别的入口进来，命中敏感词也不给播放地址
// 分类表按实测更新：t=1(电影片)/t=2(连续剧) 现在返回 0 条，已去掉；新增 t=0「最新」
var rule = {
    title: '非凡高清',
    host: 'http://ffzy5.tv',
    url: '/api.php/provide/vod/?ac=detail&t=fyclass&pg=fypage',
    searchUrl: '/api.php/provide/vod/?wd=**&pg=fypage',
    searchable: 1,
    quickSearch: 1,
    filterable: 0,
    headers: {
        'User-Agent': 'okhttp/3.14.9'
    },
    class_name: '最新&动作片&喜剧片&爱情片&科幻片&恐怖片&剧情片&战争片&国产剧&香港剧&韩国剧&欧美剧&记录片&台湾剧&日本剧&海外剧&泰国剧&大陆综艺&港台综艺&日韩综艺&欧美综艺&国产动漫&日韩动漫&欧美动漫&港台动漫&海外动漫&短剧',
    class_url: '0&6&7&8&9&10&11&12&13&14&15&16&20&21&22&23&24&25&26&27&28&29&30&31&32&33&36',

    一级: `js:
let json = JSON.parse(request(input));
let list = json.list || [];
let bad = /伦理|情色|成人|福利|午夜|三级|无码|写真|女优|裸/;
let d = [];
for (let i = 0; i < list.length; i++) {
    let v = list[i];
    let tag = (v.type_name || '') + ' ' + (v.vod_class || '');
    if (bad.test(tag) || bad.test(v.vod_name || '')) continue;
    d.push({
        title: v.vod_name || '',
        url: '/api.php/provide/vod/?ac=detail&ids=' + v.vod_id,
        img: v.vod_pic || '',
        desc: (v.vod_remarks || '') + (v.type_name ? ' · ' + v.type_name : '')
    });
}
setResult(d);`,

    搜索: `js:
let json = JSON.parse(request(input));
let list = json.list || [];
let bad = /伦理|情色|成人|福利|午夜|三级|无码|写真|女优|裸/;
let d = [];
for (let i = 0; i < list.length; i++) {
    let v = list[i];
    let tag = (v.type_name || '') + ' ' + (v.vod_class || '');
    if (bad.test(tag) || bad.test(v.vod_name || '')) continue;
    d.push({
        title: v.vod_name || '',
        url: '/api.php/provide/vod/?ac=detail&ids=' + v.vod_id,
        img: v.vod_pic || '',
        desc: (v.vod_remarks || '') + (v.type_name ? ' · ' + v.type_name : '')
    });
}
setResult(d);`,

    二级: `js:
let json = JSON.parse(request(input));
let list = json.list || [];
let v = list.length ? list[0] : null;
let bad = /伦理|情色|成人|福利|午夜|三级|无码|写真|女优|裸/;
if (!v) {
    VOD = {
        vod_id: input, vod_name: '解析失败', vod_pic: '',
        vod_play_from: '提示', vod_play_url: '返回重试$' + input
    };
} else if (bad.test((v.type_name || '') + ' ' + (v.vod_class || '') + ' ' + (v.vod_name || ''))) {
    VOD = {
        vod_id: v.vod_id, vod_name: '已屏蔽', vod_pic: '',
        vod_play_from: '提示', vod_play_url: '该内容已屏蔽$' + input
    };
} else {
    VOD = {
        vod_id: v.vod_id,
        vod_name: v.vod_name || '',
        vod_pic: v.vod_pic || '',
        type_name: v.type_name || v.vod_class || '',
        vod_year: v.vod_year || '',
        vod_area: v.vod_area || '',
        vod_remarks: v.vod_remarks || '',
        vod_content: (v.vod_content || '').replace(/<[^>]+>/g, ' ').trim(),
        vod_play_from: v.vod_play_from || '',
        vod_play_url: v.vod_play_url || ''
    };
}`
};