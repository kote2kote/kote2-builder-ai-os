import type { Env } from "./index";
import { parseChunkKey, getDoc } from "./kb";

// AI Search(旧 AutoRAG)への問い合わせ。チャンク分割・埋め込み・
// ハイブリッド検索・rerank・回答生成まで全部 Cloudflare にお任せする層。
// ★経路は専用 `ai_search` バインディング + chatCompletions() に固定する
//   (PIT-AISEARCH-005 / PIT-AISEARCH-006: search() 直呼び・旧 AI バインディング経由は
//    filters を無視 or 拒否する)。filters は新形(MongoDB 風)`{ folder: "{kb}/" }`。

export type Source = {
  kbId: string;
  docId: string;
  docName: string;
  page?: number;
  score: number;
  excerpt: string;
  hasThumb: boolean;
};

export type ChatResult = { answer: string; sources: Source[] };

type SearchChunk = {
  id: string;
  score: number;
  text: string;
  item: { key: string; timestamp?: number; metadata?: Record<string, unknown> };
};

const SYSTEM_PROMPT = [
  "あなたは社内ナレッジのサポート担当です。検索でヒットした資料の内容だけを根拠に、日本語で答えてください。",
  "ルール:",
  "- 資料に書かれていないことは推測せず、「登録された資料に記載がありません」と答える",
  "- 手順は番号付きの箇条書きで、非エンジニアにも分かる言葉で",
  "- 型番・品番・数値は資料の表記どおり正確に書く",
].join("\n");

export async function askKnowledge(
  env: Env,
  question: string,
  kbId?: string,
): Promise<ChatResult> {
  const options: Record<string, unknown> = {
    retrieval: {
      max_num_results: 8,
      retrieval_type: "hybrid",
      reranking: { enabled: true },
      // フィルタは新形(MongoDB 風)。旧 AutoRAG 形 {type:"eq",key,value} は
      // 現エンジンでは 0 件になったり他ナレッジが混入したりする(2026-08 実走確認)
      ...(kbId ? { filters: { folder: `${kbId}/` } } : {}),
    },
    query_rewrite: { enabled: true },
  };

  const response = (await env.SEARCH.chatCompletions({
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: question },
    ],
    model: env.GEN_MODEL,
    ai_search_options: options,
  })) as {
    choices?: { message?: { content?: string } }[];
    chunks?: SearchChunk[];
  };

  const answer =
    response.choices?.[0]?.message?.content?.trim() ||
    "回答を生成できませんでした。もう一度試してください。";

  const chunks = response.chunks ?? [];
  if (chunks.length === 0) {
    return {
      answer: kbId
        ? "このナレッジからは該当する記載が見つかりませんでした。索引の反映待ち(数分)か、質問の言い方を変えると見つかることがあります。"
        : "登録済みのナレッジから該当する記載が見つかりませんでした。まずナレッジに資料を登録してください。",
      sources: [],
    };
  }

  // チャンクの R2 キーから「どの資料の何ページか」を逆引きする(キー命名が契約)
  const sources: Source[] = [];
  const nameCache = new Map<string, { name: string; isPdf: boolean }>();
  for (const chunk of chunks) {
    const parsed = parseChunkKey(chunk.item.key);
    if (!parsed) continue;
    const cacheKey = `${parsed.kbId}/${parsed.docId}`;
    if (!nameCache.has(cacheKey)) {
      const doc = await getDoc(env.REGISTRY, parsed.kbId, parsed.docId);
      nameCache.set(cacheKey, { name: doc?.name ?? parsed.docId, isPdf: doc?.type === "pdf" });
    }
    const info = nameCache.get(cacheKey)!;
    sources.push({
      kbId: parsed.kbId,
      docId: parsed.docId,
      docName: info.name,
      ...(parsed.page ? { page: parsed.page } : {}),
      score: Math.round(chunk.score * 1000) / 1000,
      excerpt: chunk.text.slice(0, 220),
      hasThumb: Boolean(parsed.page && info.isPdf),
    });
  }

  return { answer, sources };
}
