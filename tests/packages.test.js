import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePackages} from '../web/packages-data.js';

const record = {number:1,name:'军训原片.zip',url:'bundles/20260912-102006/nef-01.zip',count:100,bytes:3100000000,dates:['2026-8-26','2026-8-27'],sha256:'a'.repeat(64)};
test('大于2GB的分包保持精确大小，空列表有效', () => {
  assert.equal(validatePackages({version:1,packages:[record]})[0].bytes,3100000000);
  assert.deepEqual(validatePackages({version:1,packages:[]}),[]);
});
test('拒绝目录穿越、外链、重复包号和损坏的清单', () => {
  for (const patch of [{url:'../private.zip'},{url:'https://example.org/a.zip'},{count:101},{bytes:-1},{sha256:'wrong'}]) {
    assert.throws(() => validatePackages({version:1,packages:[{...record,...patch}]}));
  }
  assert.throws(() => validatePackages({version:1,packages:[record,record]}));
});
