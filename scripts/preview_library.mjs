// 本机开发预览；生产环境必须使用 Nginx 的内部资产路由和限流。
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
const site = path.resolve(process.argv[2]);
const port = Number(process.argv[3] || 8768),
  api = Number(process.argv[4] || 8767);
const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.jpg': 'image/jpeg',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.bin': 'application/octet-stream',
};
function sendFile(name, res) {
  const file = path.resolve(site, name);
  if (!file.startsWith(site + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404);
    res.end();
    return;
  }
  res.writeHead(200, {
    'Content-Type': types[path.extname(file)] || 'application/octet-stream',
    'Cache-Control': 'no-store',
  });
  fs.createReadStream(file).pipe(res);
}
http
  .createServer((req, res) => {
    const route = new URL(req.url, 'http://localhost').pathname.slice(1);
    if (
      route === 'catalog.json' ||
      route.startsWith('api/') ||
      route.startsWith('media/') ||
      route.startsWith('downloads/')
    ) {
      const proxy = http.request(
        {
          host: '127.0.0.1',
          port: api,
          path: req.url,
          method: req.method,
          headers: { ...req.headers, 'x-forwarded-host': req.headers.host },
        },
        (response) => {
          const internal = response.headers['x-accel-redirect'];
          if (internal) {
            response.resume();
            return sendFile(internal.replace('/__litchilens_assets/', ''), res);
          }
          res.writeHead(response.statusCode, response.headers);
          response.pipe(res);
        },
      );
      proxy.on('error', () => {
        res.writeHead(502);
        res.end();
      });
      req.pipe(proxy);
    } else if (
      route === '' ||
      /^(index\.html|[a-z-]+\.(js|css|svg|png)|vendor\/[a-zA-Z0-9_./-]+)$/.test(route)
    )
      sendFile(route || 'index.html', res);
    else {
      res.writeHead(404);
      res.end();
    }
  })
  .listen(port, '127.0.0.1', () => console.log(`本机预览 http://127.0.0.1:${port}/`));
