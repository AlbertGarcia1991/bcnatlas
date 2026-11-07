import {gzipSync,gunzipSync} from 'node:zlib';
import { describe, it, expect, vi } from 'vitest';
import { route, type RouterEnv } from './router';
const path = '/api/resource/sanitat-farmacies/b89329ea-81ea-496c-9cd0-6758336e6c20';
function setup() {
  const get = vi.fn(async () => ({ body: new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode('{}')); c.close(); } }), httpEtag: '"v1"', size: 2 }));
  const head = vi.fn(async () => ({ httpEtag: '"v1"', size: 2 }));
  const assets = vi.fn(async () => new Response('app'));
  const limit = vi.fn(async () => ({ success: true }));
  const backend = vi.fn(async () => Response.json({ mappedCount: 1 }));
  const env = { ASSETS: { fetch: assets }, PUBLIC_DATA: { get, head }, PREVIEW_LIMITER: { limit }, BCN_R2_APP_PREFIX: 'app/v1.2.0' } as unknown as RouterEnv;
  const send = (p: string, init?: RequestInit) => route(new Request('https://bcnatlas.com' + p, init), env, backend);
  return { get, head, assets, limit, backend, send };
}
describe('Cloudflare routing', () => {
  it('streams allowlisted R2 assets without starting the container', async () => {
    const s = setup(); const response = await s.send('/api/data/manifest.json');
    expect(await response.json()).toEqual({});
    expect(s.get).toHaveBeenCalledWith('app/v1.2.0/data/manifest.json');
    expect(s.backend).not.toHaveBeenCalled();
    expect(response.headers.get('x-data-source')).toBe('r2');
  });
  it('handles HEAD and conditional reads', async () => {
    const s = setup(); expect(await (await s.send('/api/data/catalog.json', { method: 'HEAD' })).text()).toBe('');
    expect(s.head).toHaveBeenCalledOnce(); expect(s.get).not.toHaveBeenCalled();
    expect((await s.send('/api/data/catalog.json', { headers: { 'If-None-Match': '"v1"' } })).status).toBe(304);
  });
  it('does not turn unknown API or private-object paths into SPA HTML', async () => {
    const s = setup();
    for (const p of ['/api', '/api/data/secrets.json', '/api/data/raw/source', '/api/anything', '/api/resource/a/b']) expect((await s.send(p)).status).toBe(404);
    expect(s.get).not.toHaveBeenCalled(); expect(s.assets).not.toHaveBeenCalled();
    expect((await s.send('/api/data/catalog.json', { method: 'POST' })).status).toBe(405);
  });
  it('rejects bad filters before waking the container', async () => {
    const s = setup();
    for (const query of ['year=oops', 'url=https://example.org', 'member='+'a'.repeat(301), 'year=2023&year=2024']) expect((await s.send(path+'?'+query)).status).toBe(400);
    expect(s.backend).not.toHaveBeenCalled();
  });
  it('rate limits previews before invoking the backend', async () => {
    const s = setup(); s.limit.mockResolvedValue({ success: false });
    const r = await s.send(path, { headers: { 'CF-Connecting-IP': '192.0.2.1' } });
    expect(r.status).toBe(429); expect(r.headers.get('retry-after')).toBe('60'); expect(s.backend).not.toHaveBeenCalled();
  });
  it('preserves filters but strips caller credentials and headers', async () => {
    const s = setup(); await s.send(path+'?year=2023&member=Sheet+1', { headers: { Authorization: 'secret', Cookie: 'private', 'X-Forwarded-For': 'spoof' } });
    const request = s.backend.mock.calls[0]?.[0] as unknown as Request;
    expect(new URL(request.url).searchParams.get('member')).toBe('Sheet 1');
    expect([...request.headers.keys()]).toEqual([]);
  });
  it('contains backend and storage failures', async () => {
    const s = setup(); s.backend.mockRejectedValue(new Error('private credentials'));
    const r = await s.send(path); expect(r.status).toBe(503); expect(await r.text()).not.toContain('private credentials');
    s.get.mockRejectedValue(new Error('private endpoint')); expect((await s.send('/api/data/catalog.json')).status).toBe(503);
  });
  it('separates edge health, backend readiness and frontend routes', async () => {
    const s = setup(); expect((await s.send('/api/health')).status).toBe(200); expect(s.backend).not.toHaveBeenCalled();
    await s.send('/api/ready'); expect(new URL((s.backend.mock.calls[0]?.[0] as unknown as Request).url).pathname).toBe('/api/ready');
    expect(await (await s.send('/')).text()).toBe('app'); expect(s.assets).toHaveBeenCalledOnce();
  });
});

describe('Analytics evidence assets',()=>{
 it('streams approved analysis outputs without invoking the parser',async()=>{const s=setup();expect((await s.send('/api/analytics/manifest.json')).status).toBe(200);expect(s.get).toHaveBeenCalledWith('analytics/v1-20261107-a1/manifest.json');expect(s.backend).not.toHaveBeenCalled();});
 it('blocks arbitrary analysis paths and invalid partitions',async()=>{const s=setup();for(const path of ['/api/analytics/private.json','/api/analytics/pairs/2023-neighbourhood-32.json','/api/analytics/variables/secret.json'])expect((await s.send(path)).status).toBe(404);expect(s.get).not.toHaveBeenCalled();});
});

it('passes precompressed analytics bytes through with manual Worker encoding',async()=>{
 const s=setup();const compressed=gzipSync('{"evidence":true}');let encoding:unknown;
 s.get.mockImplementation(async()=>({body:new ReadableStream({start(c){c.enqueue(compressed);c.close();}}),httpEtag:'"gzip"',size:compressed.length,httpMetadata:{contentEncoding:'gzip'}}));
 const OriginalResponse=Response;
 class RecordedResponse extends OriginalResponse {constructor(body?:BodyInit|null,init?:ResponseInit&{encodeBody?:string}){super(body,init);encoding=init?.encodeBody;}}
 vi.stubGlobal('Response',RecordedResponse);
 try {const response=await s.send('/api/analytics/manifest.json?release=test');expect(encoding).toBe('manual');expect(response.headers.get('Content-Encoding')).toBe('gzip');expect(JSON.parse(gunzipSync(Buffer.from(await response.arrayBuffer())).toString())).toEqual({evidence:true});}finally{vi.unstubAllGlobals();}
});
