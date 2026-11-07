import { Container, getContainer } from '@cloudflare/containers';
import { route, type RouterEnv } from './router';
interface Env extends RouterEnv {
  ATLAS_API: DurableObjectNamespace<AtlasApi>;
  BCN_R2_RAW_PREFIX: string;
  BCN_R2_RAW_BUCKET: string;
  BCN_R2_PUBLIC_BUCKET: string;
  CLOUDFLARE_R2_S3_ENDPOINT: string;
  CLOUDFLARE_R2_ACCESS_KEY_ID: string;
  CLOUDFLARE_R2_ACCESS_KEY_SECRET: string;
}
export class AtlasApi extends Container<Env> {
  defaultPort = 8000;
  sleepAfter = '5m';
  enableInternet = true;
  envVars = {
    BCN_DATA_SOURCE: 'r2',
    BCN_PARSER_CONCURRENCY: '1',
    BCN_R2_APP_PREFIX: this.env.BCN_R2_APP_PREFIX,
    BCN_R2_RAW_PREFIX: this.env.BCN_R2_RAW_PREFIX,
    BCN_R2_RAW_BUCKET: this.env.BCN_R2_RAW_BUCKET,
    BCN_R2_PUBLIC_BUCKET: this.env.BCN_R2_PUBLIC_BUCKET,
    CLOUDFLARE_R2_S3_ENDPOINT: this.env.CLOUDFLARE_R2_S3_ENDPOINT || '',
    CLOUDFLARE_R2_ACCESS_KEY_ID: this.env.CLOUDFLARE_R2_ACCESS_KEY_ID || '',
    CLOUDFLARE_R2_ACCESS_KEY_SECRET: this.env.CLOUDFLARE_R2_ACCESS_KEY_SECRET || '',
  };
}
export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return route(request, env, async forwarded => {
      if (!env.CLOUDFLARE_R2_S3_ENDPOINT || !env.CLOUDFLARE_R2_ACCESS_KEY_ID || !env.CLOUDFLARE_R2_ACCESS_KEY_SECRET) {
        return Response.json({ detail: 'The preview service is awaiting server configuration.' }, { status: 503, headers: { 'Cache-Control': 'no-store' } });
      }
      return getContainer(env.ATLAS_API, 'atlas-api').fetch(forwarded);
    });
  },
};
