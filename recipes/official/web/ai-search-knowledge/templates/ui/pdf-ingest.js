// PDF のブラウザ分解 — 1 ページ = 1 ファイル(pageKey 契約)+ ページ根拠サムネイル。
// pdf.js は CDN からバージョン固定で動的ロードする。
// ★CMap 指定は必須: CID フォント(印刷入稿系の日本語 PDF)は CMap 無しだと
//   全ページ 0 文字判定になり画像扱いされる(PIT-PDFJS-001)。

const PDFJS_VERSION = "4.8.69";
const PDFJS_BASE = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}`;

// テキストページ判定の閾値(空白除去後の文字数)
const TEXT_THRESHOLD = 20;
const THUMB_WIDTH = 1980;
const THUMB_QUALITY = 0.9;

let pdfjsPromise = null;

function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import(`${PDFJS_BASE}/build/pdf.min.mjs`).then((lib) => {
      lib.GlobalWorkerOptions.workerSrc = `${PDFJS_BASE}/build/pdf.worker.min.mjs`;
      return lib;
    });
  }
  return pdfjsPromise;
}

/**
 * PDF をページ単位に分解する。
 * @returns [{ n, type: "text"|"scan", blob, thumb(dataURL) }]
 *   text ページ → blob は Markdown テキスト
 *   scan ページ → blob はページ画像 JPEG(AI Search の画像索引に読ませる)
 */
export async function splitPdf(file, onProgress) {
  const lib = await loadPdfjs();
  const data = await file.arrayBuffer();
  const doc = await lib.getDocument({
    data,
    cMapUrl: `${PDFJS_BASE}/cmaps/`,
    cMapPacked: true,
  }).promise;

  const pages = [];
  for (let n = 1; n <= doc.numPages; n++) {
    const page = await doc.getPage(n);
    const textContent = await page.getTextContent();
    let text = "";
    for (const item of textContent.items) {
      text += item.str;
      if (item.hasEOL) text += "\n";
    }
    const isText = text.replace(/\s+/g, "").length >= TEXT_THRESHOLD;

    // ページ根拠サムネイル(全ページ分。回答の根拠表示に使う)
    const thumb = await renderToDataUrl(page, THUMB_WIDTH, THUMB_QUALITY);

    let blob;
    if (isText) {
      const md = `# ${file.name} — p.${n}\n\n${text.trim()}\n`;
      blob = new Blob([md], { type: "text/markdown" });
    } else {
      // 文字が取れないページはページ画像を索引に読ませる(FEAT-01)
      blob = await renderToBlob(page, 1400, 0.85);
    }
    pages.push({ n, type: isText ? "text" : "scan", blob, thumb });
    if (onProgress) onProgress(n, doc.numPages);
  }
  await doc.destroy();
  return pages;
}

async function renderCanvas(page, targetWidth) {
  const base = page.getViewport({ scale: 1 });
  const viewport = page.getViewport({ scale: targetWidth / base.width });
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
  return canvas;
}

async function renderToDataUrl(page, targetWidth, quality) {
  const canvas = await renderCanvas(page, targetWidth);
  return canvas.toDataURL("image/jpeg", quality);
}

async function renderToBlob(page, targetWidth, quality) {
  const canvas = await renderCanvas(page, targetWidth);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}
