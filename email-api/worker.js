/* =========================================================================
   Email API — Cloudflare Worker
   Recebe POST de tarefas do Mobile e envia email via Gmail API.
   Auth: Bearer token (segredo EMAIL_TOKEN no Worker).

   Endpoints:
     POST /api/email/send
       body: { para: [emails], assunto, corpo, cc?: [emails], tarefa_id? }
       → envia via Gmail API usando OAuth refresh_token (configurado uma vez)
       → retorna {ok: true, message_id} ou {ok: false, erro}

     GET /api/email/health → {ok: true}

   Setup (UMA vez):
     1. https://console.cloud.google.com → APIs & Services → Credentials
        → Create OAuth 2.0 Client ID → Web app
        → redirect: https://developers.google.com/oauthplayground
     2. https://developers.google.com/oauthplayground
        → settings → Use your own OAuth credentials → cola client_id + secret
        → Scope: https://www.googleapis.com/auth/gmail.send
        → Authorize APIs → Exchange authorization code → copia refresh_token
     3. wrangler secret put GMAIL_CLIENT_ID
     4. wrangler secret put GMAIL_CLIENT_SECRET
     5. wrangler secret put GMAIL_REFRESH_TOKEN
     6. wrangler secret put GMAIL_FROM (ex: marcelo@3mvrepresentacao.com)
     7. wrangler secret put EMAIL_TOKEN (token forte: openssl rand -hex 32)
     8. wrangler deploy
   ========================================================================= */

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Max-Age': '86400',
};

function jsonResp(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...CORS },
  });
}

function auth(req, env) {
  const h = req.headers.get('Authorization') || '';
  const m = h.match(/^Bearer\s+(.+)$/i);
  if (!m) return false;
  return m[1] === env.EMAIL_TOKEN;
}

async function gmailAccessToken(env) {
  const body = new URLSearchParams({
    client_id: env.GMAIL_CLIENT_ID,
    client_secret: env.GMAIL_CLIENT_SECRET,
    refresh_token: env.GMAIL_REFRESH_TOKEN,
    grant_type: 'refresh_token',
  });
  const r = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  const j = await r.json();
  if (!j.access_token) throw new Error('Falha access_token: ' + JSON.stringify(j));
  return j.access_token;
}

function encodeSubjectUtf8(s) {
  // RFC 2047 — codifica subject UTF-8 em base64 pra preservar acentos
  if (!/[^\x00-\x7F]/.test(s)) return s;
  const b64 = btoa(unescape(encodeURIComponent(s)));
  return '=?UTF-8?B?' + b64 + '?=';
}

function detectaHtml(body) {
  if (typeof body !== 'string') return false;
  const trimmed = body.trim().toLowerCase();
  return trimmed.startsWith('<!doctype') ||
         trimmed.startsWith('<html') ||
         /<(p|div|span|table|h[1-6]|br|a|b|strong|em|ul|ol|li|img|body)\b/i.test(trimmed.slice(0, 500));
}

function buildRfc822({ from, to, cc, subject, body, tipo }) {
  const isHtml = (tipo === 'html') || (tipo !== 'plain' && detectaHtml(body));
  const contentType = isHtml ? 'text/html; charset=UTF-8' : 'text/plain; charset=UTF-8';
  // base64 pra qualquer corpo (HTML ou plain) — garante que acentos cheguem inteiros
  const b64body = btoa(unescape(encodeURIComponent(body)))
                    .replace(/(.{76})/g, '$1\r\n');
  const headers = [
    `From: ${from}`,
    `To: ${(Array.isArray(to) ? to : [to]).join(', ')}`,
    cc && cc.length ? `Cc: ${(Array.isArray(cc) ? cc : [cc]).join(', ')}` : '',
    `Subject: ${encodeSubjectUtf8(subject)}`,
    'MIME-Version: 1.0',
    `Content-Type: ${contentType}`,
    'Content-Transfer-Encoding: base64',
  ].filter(x => x).join('\r\n');
  return headers + '\r\n\r\n' + b64body;
}

function b64UrlEncode(str) {
  // RFC4648 base64url (sem padding)
  const b64 = btoa(unescape(encodeURIComponent(str)));
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export default {
  async fetch(req, env) {
    if (req.method === 'OPTIONS') return new Response(null, { headers: CORS });
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, '');

    if (path === '/api/email/health' || path === '/api/email') {
      return jsonResp({ ok: true, ts: new Date().toISOString() });
    }

    if (!auth(req, env)) {
      return jsonResp({ erro: 'unauthorized' }, 401);
    }

    if (req.method === 'POST' && path === '/api/email/send') {
      try {
        const data = await req.json();
        const { para, assunto, corpo, cc, tipo, tarefa_id } = data;
        if (!para || !assunto || !corpo) {
          return jsonResp({ erro: 'campos obrigatorios: para, assunto, corpo' }, 400);
        }
        const at = await gmailAccessToken(env);
        const rfc = buildRfc822({
          from: env.GMAIL_FROM || 'marcelo@3mvrepresentacao.com',
          to: para,
          cc: cc,
          subject: assunto,
          body: corpo,
          tipo: tipo,
        });
        const raw = b64UrlEncode(rfc);
        const sendResp = await fetch(
          'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${at}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ raw }),
          }
        );
        const sendJson = await sendResp.json();
        if (!sendResp.ok) {
          return jsonResp({ ok: false, erro: sendJson }, 500);
        }
        return jsonResp({ ok: true, message_id: sendJson.id, tarefa_id });
      } catch (e) {
        return jsonResp({ ok: false, erro: e.message }, 500);
      }
    }

    return jsonResp({ erro: 'rota_nao_encontrada', path, method: req.method }, 404);
  },
};
