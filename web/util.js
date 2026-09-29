// 화면 여기저기서 쓰는 최소한의 도구.

export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];

export const KIND_KO = {
  actors: "배우", costumes: "의상", scenes: "장소",
  props: "소품", layouts: "레이아웃", voices: "음성",
};

export async function api(path, opts) {
  const r = await fetch(path, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}

export function el(tag, opts = {}, kids = []) {
  const n = document.createElement(tag);
  if (opts.class) n.className = opts.class;
  if (opts.text != null) n.textContent = opts.text;
  if (opts.html != null) n.innerHTML = opts.html;
  for (const [k, v] of Object.entries(opts.attr || {})) n.setAttribute(k, v);
  for (const [k, v] of Object.entries(opts.on || {})) n.addEventListener(k, v);
  for (const c of kids) if (c) n.appendChild(c);
  return n;
}

export function showView(name) {
  $$(".nav").forEach((x) => x.classList.toggle("on", x.dataset.view === name));
  $$(".view").forEach((s) => s.classList.toggle("on", s.id === "v-" + name));
}
