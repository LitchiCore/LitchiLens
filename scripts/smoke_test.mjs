// 真实演示文件 + 本机 API + 浏览器下载，不依赖线上服务器或私人照片。
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const site = path.join(root, 'output/demo/site');
const children = [];
let browser;
function start(command, args) {
  const child = spawn(command, args, { cwd: root, stdio: 'inherit', windowsHide: true });
  child.on('error', (error) => console.error(error.message));
  children.push(child);
}
try {
  const catalog = JSON.parse(fs.readFileSync(path.join(site, 'catalog.json')));
  assert.equal(catalog.photos.length, 3);
  start(process.env.PYTHON || 'python', [
    'deploy/library_server.py',
    '--site',
    site,
    '--state',
    'output/demo/state.json',
    '--port',
    '18767',
    '--admin-port',
    '18769',
  ]);
  start(process.execPath, ['scripts/preview_library.mjs', site, '18768', '18767']);
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      const response = await fetch('http://127.0.0.1:18768/catalog.json');
      if (response.ok) {
        ready = true;
        break;
      }
    } catch {
      /* 等待本机服务启动。 */
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  assert.ok(ready, '本机演示服务未就绪');
  browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
  });
  const page = await browser.newPage({
    viewport: { width: 393, height: 852 },
    acceptDownloads: true,
  });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('http://127.0.0.1:18768/');
  assert.ok(await page.locator('#home').isVisible());
  assert.ok(await page.locator('.header-links [data-support-open]').isHidden());
  await page.locator('.home-choices a[href="#library"]').click();
  await page.locator('.photo').first().waitFor();
  assert.equal(await page.locator('.photo').count(), 3);
  await page.locator('.check-photo input').first().check();
  await page.locator('#batch-download').click();
  await page.locator('#prepare-download').click();
  await page.locator('#download-files a').waitFor();
  assert.ok(await page.locator('#zip-link').isHidden());
  const pending = page.waitForEvent('download');
  await page.locator('#download-files a').click();
  const download = await pending;
  assert.equal(await download.failure(), null);
  assert.equal(download.suggestedFilename(), `${catalog.photos[0].id}.jpg`);
  assert.deepEqual(
    fs.readFileSync(await download.path()),
    fs.readFileSync(path.join(site, catalog.photos[0].jpg.url)),
  );
  await download.delete();
  await page.locator('[data-close="download-dialog"]').click();
  await page.locator('#library a[href="#home"]').click();
  await page.locator('#home').waitFor({ state: 'visible' });
  assert.deepEqual(errors, []);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  console.log('演示验证通过：真实构建、目录、手机布局、原文件下载和回首页。');
} finally {
  await browser?.close();
  for (const child of children) child.kill();
}
