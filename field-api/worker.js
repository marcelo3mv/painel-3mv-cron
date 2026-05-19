/* =========================================================================
   Field API - Cloudflare Worker
   Backend de escrita do 3MV Field. Recebe atas/visitas/tarefas do app mobile
   e armazena no KV. Exposto em: https://field-api.marcelo-778.workers.dev

   Endpoints HTTP:
     POST   /api/field/atas       body: {id, cliente, data, resumo, usuario}
     POST   /api/field/visitas    body: {id, cliente, data, usuario}
     POST   /api/field/tarefas    body: {id, cliente, texto, responsavel, feita, data, usuario}
     PUT    /api/field/tarefas    body: {id, ..., feita}  (atualiza)
     GET    /api/field/state      retorna {atas[], visitas[], tarefas[]}
     GET    /api/field/snapshot   retorna JSON estruturado para injetar no dados.json
     DELETE /api/field/atas/:id   remove
     GET    /api/field/confirmar?id=X&acao=Y   link público de confirmação (do email)

   CRON (scheduled): a cada hora — verifica tarefas atrasadas e envia
   cobrança via MailChannels (email gratuito do Cloudflare Workers).

   Auth: Bearer token (segredo FIELD_TOKEN configurado no Worker).
   Email: usa MailChannels (sem API key, free for CF Workers).
   ========================================================================= */

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Access-Control-Max-Age': '86400',
};

const EQUIPE = [
  { nome: 'Marcelo', email: 'marcelo@3mvrepresentacao.com', whats: '5531988843675' },
  { nome: 'Lais',    email: 'adm@3mvrepresentacao.com',     whats: '5531999403675' },
  { nome: 'Rafa',    email: 'adm1@3mvrepresentacao.com',    whats: '5531999403675' },
];

function jsonResp(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...CORS },
  });
}

function htmlResp(html, status) {
  return new Response(html, {
    status: status || 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS },
  });
}

function auth(req, env) {
  const h = req.headers.get('Authorization') || '';
  const m = h.match(/^Bearer\s+(.+)$/i);
  if (!m) return false;
  return m[1] === env.FIELD_TOKEN;
}

async function readIdx(env, kind) {
  const v = await env.FIELD.get('idx:' + kind);
  return v ? JSON.parse(v) : [];
}
async function writeIdx(env, kind, ids) {
  await env.FIELD.put('idx:' + kind, JSON.stringify(ids));
}

async function upsert(env, kind, item) {
  if (!item || !item.id) throw new Error('id obrigatorio');
  await env.FIELD.put(kind + ':' + item.id, JSON.stringify(item));
  const idx = await readIdx(env, kind);
  if (!idx.includes(item.id)) {
    idx.push(item.id);
    await writeIdx(env, kind, idx);
  }
}

async function listAll(env, kind) {
  const idx = await readIdx(env, kind);
  const out = [];
  await Promise.all(idx.map(async id => {
    const v = await env.FIELD.get(kind + ':' + id);
    if (v) out.push(JSON.parse(v));
  }));
  return out;
}

async function getOne(env, kind, id) {
  const v = await env.FIELD.get(kind + ':' + id);
  return v ? JSON.parse(v) : null;
}

async function removeItem(env, kind, id) {
  await env.FIELD.delete(kind + ':' + id);
  const idx = await readIdx(env, kind);
  const novo = idx.filter(x => x !== id);
  await writeIdx(env, kind, novo);
}

// === Gmail API: envia email autenticado como marcelo@3mvrepresentacao.com ===
// Secrets necessárias: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
async function _gmailAccessToken(env) {
  const r = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: env.GMAIL_CLIENT_ID,
      client_secret: env.GMAIL_CLIENT_SECRET,
      refresh_token: env.GMAIL_REFRESH_TOKEN,
      grant_type: 'refresh_token',
    }),
  });
  if (!r.ok) throw new Error('oauth_refresh_failed:' + (await r.text()).slice(0,120));
  const j = await r.json();
  return j.access_token;
}

function _b64urlUtf8(str) {
  const b = btoa(unescape(encodeURIComponent(str)));
  return b.replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}

async function enviarEmail(env, { to, subject, html, replyTo }) {
  const fromAddr = env.MAIL_FROM || 'marcelo@3mvrepresentacao.com';
  const fromName = '3MV Tarefas (auto)';
  const toList = (Array.isArray(to) ? to : [to]).filter(Boolean).join(', ');
  const subjEnc = '=?UTF-8?B?' + btoa(unescape(encodeURIComponent(subject))) + '?=';
  const headers = [
    `From: ${fromName} <${fromAddr}>`,
    `To: ${toList}`,
    `Subject: ${subjEnc}`,
    `MIME-Version: 1.0`,
    `Content-Type: text/html; charset="UTF-8"`,
    `Content-Transfer-Encoding: 8bit`,
  ];
  if (replyTo) headers.push(`Reply-To: ${replyTo}`);
  const rawMime = headers.join('\r\n') + '\r\n\r\n' + html;
  try {
    const token = await _gmailAccessToken(env);
    const r = await fetch('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
      body: JSON.stringify({ raw: _b64urlUtf8(rawMime) }),
    });
    return { ok: r.ok, status: r.status, text: r.ok ? '' : (await r.text()).slice(0,200) };
  } catch (e) {
    return { ok: false, status: 0, text: e.message };
  }
}

function _dias(dataStr) {
  if (!dataStr) return 0;
  let d;
  const partes = dataStr.includes('/') ? dataStr.split('/') : null;
  if (partes && partes.length === 3) d = new Date(+partes[2], +partes[1]-1, +partes[0]);
  else d = new Date(dataStr);
  if (isNaN(d.getTime())) return 0;
  return Math.max(0, Math.round((Date.now() - d.getTime()) / 86400000));
}

function _msg(t, urlBase) {
  const respList = Array.isArray(t.responsavel) ? t.responsavel : [t.responsavel];
  const dias = _dias(t.data);
  const prazo = t.prazo_dias || 2;
  const idEnc = encodeURIComponent(t.id);
  const linkExec = `${urlBase}/api/field/confirmar?id=${idEnc}&acao=executei`;
  const linkVista = `${urlBase}/api/field/confirmar?id=${idEnc}&acao=vista`;
  const linkRecusa = `${urlBase}/api/field/confirmar?id=${idEnc}&acao=recusa`;
  return `<!doctype html><html><body style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:20px;color:#1e293b;">
    <h2 style="color:#dc2626;margin:0 0 8px;">🔔 Cobrança automática 3MV</h2>
    <p style="font-size:14px;color:#64748b;margin:0 0 16px;">Tarefa há <b>${dias} dia(s)</b> sem resposta (prazo: ${prazo}d).</p>
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #dc2626;border-radius:8px;padding:16px;margin:14px 0;">
      <div style="font-size:15px;font-weight:700;color:#1e3a8a;margin-bottom:8px;">${t.texto || ''}</div>
      <div style="font-size:12px;color:#475569;line-height:1.6;">
        ${t.cliente ? `📍 <b>Cliente:</b> ${t.cliente}<br>` : ''}
        ${t.industria ? `🏭 <b>Indústria:</b> ${t.industria}<br>` : ''}
        📅 <b>Criada em:</b> ${t.data}<br>
        👥 <b>Para:</b> ${respList.join(', ')}<br>
        ⚡ <b>Prioridade:</b> ${(t.prioridade || 'media').toUpperCase()}
      </div>
    </div>
    <p style="font-size:13px;margin:14px 0 8px;"><b>Confirme abaixo o que vai fazer:</b></p>
    <p style="margin:0 0 6px;">
      <a href="${linkExec}" style="display:inline-block;background:#16a34a;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:700;margin-right:6px;">✓ Já executei</a>
      <a href="${linkVista}" style="display:inline-block;background:#3b82f6;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:700;margin-right:6px;">👁 Vi, vou fazer</a>
      <a href="${linkRecusa}" style="display:inline-block;background:#f59e0b;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:700;">⏰ Adiar</a>
    </p>
    <p style="font-size:11px;color:#94a3b8;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:12px;">
      Você está recebendo esse email porque é responsável pela tarefa no painel 3MV.<br>
      <a href="https://painel.3mvrepresentacao.com" style="color:#3b82f6;">painel.3mvrepresentacao.com</a>
    </p>
  </body></html>`;
}

// === Cron handler: roda no schedule configurado em wrangler.toml ===
async function rodarCron(env) {
  const tarefas = await listAll(env, 'tarefas');
  const urlBase = env.SELF_URL || 'https://field-api.marcelo-778.workers.dev';
  const enviadas = [];
  for (const t of tarefas) {
    if (t.feita || t.respondida_em) continue;
    const dias = _dias(t.data);
    const prazo = t.prazo_dias || 2;
    if (dias < prazo) continue;
    // Já cobrado nas últimas 24h?
    const envios = t.envios || [];
    const ult = envios[envios.length - 1];
    if (ult && ult.quando) {
      const qd = new Date(ult.quando.replace(' ', 'T'));
      if (!isNaN(qd.getTime()) && (Date.now() - qd.getTime()) < 24*60*60*1000) continue;
    }
    // Determina destinatários: se reportar_para=cliente, manda pra equipe inteira (Marcelo+Lais+Rafa). Senão, só os responsáveis.
    const respList = Array.isArray(t.responsavel) ? t.responsavel : [t.responsavel];
    const destinos = (t.reportar_para === 'cliente')
      ? EQUIPE
      : EQUIPE.filter(m => respList.includes(m.nome));
    if (!destinos.length) continue;
    const emails = destinos.map(d => d.email).filter(Boolean);
    if (!emails.length) continue;
    const r = await enviarEmail(env, {
      to: emails,
      subject: `🔔 [3MV COBRANÇA] ${(t.texto || '').slice(0, 60)} (${dias}d)`,
      html: _msg(t, urlBase),
    });
    t.envios = t.envios || [];
    t.envios.push({
      canal: 'email',
      quando: new Date().toISOString().slice(0,16).replace('T', ' '),
      por: 'cron-auto',
      status: r.ok ? 'enviado' : 'falha:' + r.text.slice(0,80),
      tipo: 'cobrança-auto-cron',
      destinatarios: emails,
    });
    t._editadoEm = Date.now();
    await upsert(env, 'tarefas', t);
    enviadas.push({ id: t.id, emails, ok: r.ok, status: r.status });
  }
  return enviadas;
}

export default {
  async fetch(req, env) {
    if (req.method === 'OPTIONS') return new Response(null, { headers: CORS });

    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, '');

    // Health check publico
    if (path === '/api/field/health' || path === '/api/field') {
      return jsonResp({ ok: true, ts: new Date().toISOString() });
    }

    // Link público de confirmação (vem do email — sem auth)
    if (path === '/api/field/confirmar' && req.method === 'GET') {
      const id = url.searchParams.get('id') || '';
      const acao = url.searchParams.get('acao') || '';
      if (!id || !acao) return htmlResp('<h3>Link inválido</h3>', 400);
      const t = await getOne(env, 'tarefas', id);
      if (!t) return htmlResp('<h3>Tarefa não encontrada</h3>', 404);
      const agora = new Date().toISOString().slice(0,16).replace('T',' ');
      let msg = '';
      if (acao === 'executei') {
        t.feita = true;
        t.concluida_em = agora;
        t.executado_por = 'destinatário (via email)';
        t.respondida_em = agora;
        msg = '✅ Marcado como EXECUTADO. Obrigado!';
      } else if (acao === 'vista') {
        t.vista_em = agora;
        t.vista_por = 'destinatário (via email)';
        msg = '👁 Marcado como VISTO — você vai executar em breve.';
      } else if (acao === 'recusa') {
        t.adiada_em = agora;
        t.adiamentos = (t.adiamentos || 0) + 1;
        msg = '⏰ Adiamento registrado. Cobrança volta em 24h.';
      } else {
        return htmlResp('<h3>Ação inválida</h3>', 400);
      }
      t._editadoEm = Date.now();
      await upsert(env, 'tarefas', t);
      return htmlResp(`<!doctype html><html><body style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:480px;margin:60px auto;padding:24px;text-align:center;color:#1e293b;">
        <div style="font-size:48px;margin-bottom:14px;">${acao==='executei'?'✅':(acao==='vista'?'👁':'⏰')}</div>
        <h2 style="color:#1e3a8a;">${msg}</h2>
        <p style="color:#64748b;font-size:13px;">Tarefa: <b>${t.texto||''}</b></p>
        <p style="margin-top:24px;"><a href="https://painel.3mvrepresentacao.com" style="background:#3b82f6;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:700;">Abrir painel 3MV</a></p>
      </body></html>`);
    }

    // Tudo abaixo exige Bearer
    if (!auth(req, env)) {
      return jsonResp({ erro: 'unauthorized' }, 401);
    }

    try {
      // GET /api/field/state
      if (req.method === 'GET' && path === '/api/field/state') {
        const [atas, visitas, tarefas] = await Promise.all([
          listAll(env, 'atas'), listAll(env, 'visitas'), listAll(env, 'tarefas'),
        ]);
        return jsonResp({ atas, visitas, tarefas, geradoEm: new Date().toISOString() });
      }
      if (req.method === 'GET' && path === '/api/field/snapshot') {
        const [atas, visitas, tarefas] = await Promise.all([
          listAll(env, 'atas'), listAll(env, 'visitas'), listAll(env, 'tarefas'),
        ]);
        const ultimaVisitaPorCliente = {};
        for (const v of visitas) {
          if (!ultimaVisitaPorCliente[v.cliente] || v.data > ultimaVisitaPorCliente[v.cliente].data) {
            ultimaVisitaPorCliente[v.cliente] = { data: v.data, usuario: v.usuario };
          }
        }
        return jsonResp({
          atas, visitas, tarefas,
          agregados: {
            total_atas: atas.length, total_visitas: visitas.length,
            total_tarefas: tarefas.length,
            tarefas_pendentes: tarefas.filter(t => !t.feita).length,
            ultima_visita_por_cliente: ultimaVisitaPorCliente,
          },
          geradoEm: new Date().toISOString(),
        });
      }
      // POST/PUT /api/field/<kind>s
      const m = path.match(/^\/api\/field\/(atas|visitas|tarefas)$/);
      if (m && (req.method === 'POST' || req.method === 'PUT')) {
        const kind = m[1];
        const body = await req.json();
        if (!body.id) body.id = crypto.randomUUID();
        body._salvoEm = new Date().toISOString();
        await upsert(env, kind, body);
        return jsonResp({ ok: true, item: body });
      }
      // DELETE /api/field/<kind>/<id>
      const m2 = path.match(/^\/api\/field\/(atas|visitas|tarefas)\/([^\/]+)$/);
      if (m2 && req.method === 'DELETE') {
        await removeItem(env, m2[1], decodeURIComponent(m2[2]));
        return jsonResp({ ok: true });
      }
      // POST /api/field/cron/run — dispara cron manualmente (debug)
      if (req.method === 'POST' && path === '/api/field/cron/run') {
        const enviadas = await rodarCron(env);
        return jsonResp({ ok: true, enviadas });
      }
      return jsonResp({ erro: 'rota_nao_encontrada', path, method: req.method }, 404);
    } catch (e) {
      return jsonResp({ erro: 'falha', msg: e.message }, 500);
    }
  },

  // ==== CRON HANDLER ====
  async scheduled(event, env, ctx) {
    ctx.waitUntil(rodarCron(env));
  },
};
