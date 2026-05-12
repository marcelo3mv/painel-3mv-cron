/* =========================================================================
   Field API - Cloudflare Worker
   Backend de escrita do 3MV Field. Recebe atas/visitas/tarefas do app mobile
   e armazena no KV. Exposto em: https://field-api.3mvrepresentacao.com
   (ou em rota relativa do painel: /api/field/* via Workers Route)

   Endpoints:
     POST   /api/field/atas       body: {id, cliente, data, resumo, usuario}
     POST   /api/field/visitas    body: {id, cliente, data, usuario}
     POST   /api/field/tarefas    body: {id, cliente, texto, responsavel, feita, data, usuario}
     PUT    /api/field/tarefas    body: {id, ..., feita}  (atualiza)
     GET    /api/field/state      retorna {atas[], visitas[], tarefas[]}
     GET    /api/field/snapshot   retorna JSON estruturado para injetar no dados.json
     DELETE /api/field/atas/:id   remove

   Auth: Bearer token (segredo FIELD_TOKEN configurado no Worker).

   Storage: KV namespace "FIELD" com chaves:
     atas:<id>      -> JSON do ata
     visitas:<id>   -> JSON da visita
     tarefas:<id>   -> JSON da tarefa
     idx:atas       -> JSON array de ids (atualizado em cada POST)
     idx:visitas    -> JSON array de ids
     idx:tarefas    -> JSON array de ids

   Deploy:
     1) wrangler kv namespace create FIELD
     2) Copie o id retornado para wrangler.toml
     3) wrangler secret put FIELD_TOKEN   (gera um token forte: openssl rand -hex 32)
     4) wrangler deploy
     5) Configure DNS field-api.3mvrepresentacao.com -> Worker (Cloudflare Dashboard)
   ========================================================================= */

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
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
  // KV nao tem multi-get nativo, mas paraleliza bem
  await Promise.all(idx.map(async id => {
    const v = await env.FIELD.get(kind + ':' + id);
    if (v) out.push(JSON.parse(v));
  }));
  return out;
}

async function removeItem(env, kind, id) {
  await env.FIELD.delete(kind + ':' + id);
  const idx = await readIdx(env, kind);
  const novo = idx.filter(x => x !== id);
  await writeIdx(env, kind, novo);
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

    // Tudo abaixo exige Bearer
    if (!auth(req, env)) {
      return jsonResp({ erro: 'unauthorized' }, 401);
    }

    try {
      // GET /api/field/state
      if (req.method === 'GET' && path === '/api/field/state') {
        const [atas, visitas, tarefas] = await Promise.all([
          listAll(env, 'atas'),
          listAll(env, 'visitas'),
          listAll(env, 'tarefas'),
        ]);
        return jsonResp({ atas, visitas, tarefas, geradoEm: new Date().toISOString() });
      }

      // GET /api/field/snapshot - mesma coisa mas com agregados (consumido pelo injetar_field.py)
      if (req.method === 'GET' && path === '/api/field/snapshot') {
        const [atas, visitas, tarefas] = await Promise.all([
          listAll(env, 'atas'),
          listAll(env, 'visitas'),
          listAll(env, 'tarefas'),
        ]);
        // Agregados uteis para o Painel
        const ultimaVisitaPorCliente = {};
        for (const v of visitas) {
          if (!ultimaVisitaPorCliente[v.cliente] || v.data > ultimaVisitaPorCliente[v.cliente].data) {
            ultimaVisitaPorCliente[v.cliente] = { data: v.data, usuario: v.usuario };
          }
        }
        const tarefasPendentes = tarefas.filter(t => !t.feita).length;
        return jsonResp({
          atas, visitas, tarefas,
          agregados: {
            total_atas: atas.length,
            total_visitas: visitas.length,
            total_tarefas: tarefas.length,
            tarefas_pendentes: tarefasPendentes,
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

      return jsonResp({ erro: 'rota_nao_encontrada', path, method: req.method }, 404);
    } catch (e) {
      return jsonResp({ erro: 'falha', msg: e.message }, 500);
    }
  },
};
