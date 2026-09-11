import test from 'node:test';
import assert from 'node:assert/strict';
import {filterPhotos, safeAsset, validateCatalog} from '../web/catalog.js';

test('日期与编号联合筛选，保留照片原顺序', () => {
  const photos = [{name:'DSC_0001.jpg',date:'2026-08-26'},{name:'DSC_0001.jpg',date:'2026-08-27'},{name:'DSC_0002.jpg',date:'2026-08-26'}];
  assert.deepEqual(filterPhotos(photos,'2026-08-26','dsc_0001'), [photos[0]]);
  assert.equal(filterPhotos(photos,'','  ').length,3);
  assert.equal(filterPhotos(photos,'','不存在').length,0);
});
test('下载地址不能逃离分享路径或引用外部 URL', () => {
  for (const path of ['../secret.jpg','/downloads/abc.jpg','https://other.test/a.jpg','javascript:alert(1)','media/../abc.jpg','downloads/abc.jpg?x=1']) assert.throws(() => safeAsset(path));
  assert.equal(safeAsset('downloads/a012-abc.nef'),'downloads/a012-abc.nef');
});
test('空相册有效，错误索引和重复记录必须拒绝', () => {
  assert.equal(validateCatalog({version:1,title:'军训',dates:[],photos:[]}).photos.length,0);
  assert.throws(() => validateCatalog({version:2,dates:[],photos:[]}));
  const p={id:'a',name:'照片.jpg',date:'2026-08-26',thumb:'media/a-0.jpg',preview:'media/a-1.jpg',jpg:{url:'downloads/a.jpg'}};
  assert.throws(() => validateCatalog({version:1,title:'相册',dates:[p.date],photos:[p,p]}));
});
