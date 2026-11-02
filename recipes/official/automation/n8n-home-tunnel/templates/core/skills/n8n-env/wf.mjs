// n8n のワークフローを一覧 / 書き出し / 読み込みする(REST API。手元の 127.0.0.1 へ直接つなぐ)
// 使い方(プロジェクト直下で):
//   node --env-file=.env .claude/skills/n8n-env/wf.mjs list
//   node --env-file=.env .claude/skills/n8n-env/wf.mjs export <workflowId>
//   node --env-file=.env .claude/skills/n8n-env/wf.mjs import workflows/<file>.json
// API キーは .env の N8N_API_KEY から読む。画面には出さない。
import { writeFileSync, readFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const port = process.env.N8N_LOCAL_PORT;
if (!port) {
  console.error('N8N_LOCAL_PORT が .env にありません(プロジェクト直下で node --env-file=.env ... として実行してください)');
  process.exit(1);
}
const base = `http://127.0.0.1:${port}/api/v1`;
const key = process.env.N8N_API_KEY;
if (!key) {
  console.error('N8N_API_KEY が .env に入っていません。n8n の Settings > n8n API で発行し、.env に自分で貼ってください(チャットには貼らない)');
  process.exit(1);
}

// PUT / POST が受け付ける settings だけに絞る(GET は UI 用の設定も返すが、送ると弾かれる)
const SETTINGS_KEYS = ['timezone', 'executionOrder', 'saveDataErrorExecution', 'saveDataSuccessExecution',
  'saveManualExecutions', 'saveExecutionProgress', 'errorWorkflow', 'executionTimeout'];
const pickSettings = (s = {}) => Object.fromEntries(Object.entries(s).filter(([k]) => SETTINGS_KEYS.includes(k)));

async function api(method, path, body) {
  const res = await fetch(base + path, {
    method,
    headers: { 'X-N8N-API-KEY': key, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${path} → HTTP ${res.status}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

const safeName = (s) => s.replace(/[\\/:*?"<>|\s]+/g, '-').replace(/^-+|-+$/g, '') || 'workflow';

const [cmd, arg] = process.argv.slice(2);
try {
  if (cmd === 'list') {
    let cursor = '';
    do {
      const r = await api('GET', `/workflows?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
      for (const w of r.data) console.log(`${w.id}\t${w.active ? '有効' : '停止'}\t${w.name}`);
      cursor = r.nextCursor || '';
    } while (cursor);
  } else if (cmd === 'export' && arg) {
    const w = await api('GET', `/workflows/${encodeURIComponent(arg)}`);
    // 配布用: 実行に必要な部分だけ残す(ID・有効状態・共有情報・テスト用の固定データは外す)
    const out = { name: w.name, nodes: w.nodes, connections: w.connections, settings: pickSettings(w.settings) };
    mkdirSync('workflows', { recursive: true });
    const file = join('workflows', `${safeName(w.name)}.json`);
    writeFileSync(file, JSON.stringify(out, null, 2) + '\n');
    const creds = [...new Set(w.nodes.flatMap((n) => Object.values(n.credentials || {}).map((c) => c.name)))];
    console.log(`書き出し: ${file}`);
    if (creds.length) console.log(`このワークフローが使う認証情報(中身は含まれません。読み込み先で作り直し): ${creds.join(', ')}`);
  } else if (cmd === 'import' && arg) {
    const w = JSON.parse(readFileSync(arg, 'utf8'));
    const r = await api('POST', '/workflows', {
      name: w.name, nodes: w.nodes, connections: w.connections, settings: pickSettings(w.settings),
    });
    console.log(`読み込み: ${r.name}(id ${r.id}・停止状態で作成。認証情報を設定してから有効化)`);
  } else {
    console.log('使い方: list | export <workflowId> | import <file.json>');
    process.exit(1);
  }
} catch (e) {
  console.error(String(e.message || e));
  process.exit(1);
}
