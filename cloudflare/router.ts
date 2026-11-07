export interface RouterEnv {
  ASSETS: Fetcher;
  PUBLIC_DATA: R2Bucket;
  PREVIEW_LIMITER: RateLimit;
  BCN_R2_APP_PREFIX: string;
}
export type Backend = (request: Request) => Promise<Response>;
const assetName = /^(?:(?:catalog|manifest|mirror-status)|(?:accidents|street-trees|park-trees)-\d{4})\.json$/;
const resourcePath = /^\/api\/resource\/[a-z0-9_-]+\/[a-f0-9-]{36}$/;
const jsonError = (detail: string, status: number, headers = {}) => Response.json({ detail }, { status, headers: { 'Cache-Control': 'no-store', ...headers } });

export async function route(request: Request, env: RouterEnv, backend: Backend): Promise<Response> {
  const url = new URL(request.url);
  if (url.pathname !== '/api' && !url.pathname.startsWith('/api/')) return env.ASSETS.fetch(request);
  if (!['GET', 'HEAD'].includes(request.method)) return jsonError('Only GET and HEAD are supported.', 405, { Allow: 'GET, HEAD' });
  if (url.pathname === '/api/health') return Response.json({ status: 'ok', service: 'bcnatlas-edge', dataSource: 'r2' });
  if (url.pathname.startsWith('/api/data/')) {
    const name = url.pathname.slice('/api/data/'.length);
    if (!assetName.test(name)) return jsonError('Unknown data asset.', 404);
    try {
      const key = `${env.BCN_R2_APP_PREFIX}/data/${name}`;
      const object = request.method === 'HEAD' ? await env.PUBLIC_DATA.head(key) : await env.PUBLIC_DATA.get(key);
      if (!object) return jsonError('This data asset is not available in R2.', 404);
      const headers = new Headers({ 'Content-Type': 'application/json', 'Cache-Control': name === 'mirror-status.json' ? 'public, max-age=60' : 'public, max-age=300', 'ETag': object.httpEtag, 'X-Data-Source': 'r2', 'X-Content-Type-Options': 'nosniff' });
      if (request.headers.get('If-None-Match') === object.httpEtag) return new Response(null, { status: 304, headers });
      headers.set('Content-Length', String(object.size));
      return new Response('body' in object ? object.body as ReadableStream : null, { headers });
    } catch { return jsonError('Data storage is temporarily unavailable. Please retry.', 503); }
  }
  if (request.method !== 'GET') return jsonError('This endpoint requires GET.', 405, { Allow: 'GET' });
  const readiness = url.pathname === '/api/ready';
  if (!readiness && !resourcePath.test(url.pathname)) return jsonError('Unknown API route.', 404);
  if ([...url.searchParams.keys()].some(k => !['member', 'year', 'filters'].includes(k)) || url.searchParams.getAll('filters').length > 1 || (url.searchParams.get('filters') || '').length > 4096 || url.searchParams.getAll('year').length > 1 || url.searchParams.getAll('member').length > 1 || (url.searchParams.get('member') || '').length > 300 || (url.searchParams.has('year') && !/^(19|20)\d{2}$/.test(url.searchParams.get('year')!))) return jsonError('Invalid resource filters.', 400);
  try {
    const allowed = await env.PREVIEW_LIMITER.limit({ key: request.headers.get('CF-Connecting-IP') || 'unknown' });
    if (!allowed.success) return jsonError('Too many preview requests. Please retry in a minute.', 429, { 'Retry-After': '60' });
    // Forward only the route and query. Cookies, client authorization and spoofed headers never reach the parser.
    const target = new URL('http://container');
    target.pathname = readiness ? '/api/ready' : url.pathname;
    target.search = url.search;
    return await backend(new Request(target, { method: request.method, signal: request.signal }));
  } catch { return jsonError('The preview service is starting or temporarily unavailable. Please retry shortly.', 503, { 'Retry-After': '10' }); }
}
