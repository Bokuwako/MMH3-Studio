// MMH3 Studio — 화면. 서버가 /api 로 주는 것만 그린다.

import { $, $$, api, el, KIND_KO } from "/web/util.js";
import { Director, wireDirector } from "/web/director.js";
import { Production, wireProduction, Projects, wireProjects } from "/web/production.js";
import { Casting, wireCasting } from "/web/casting.js";
import { Refs, wireRefs } from "/web/refs.js";
import { wireWorkflows, paintWorkflows } from "/web/workflows.js";

/* ─────────────────────────────────────────────── 네비 */

$$(".nav").forEach((a) => a.addEventListener("click", () => {
  $$(".nav").forEach((x) => x.classList.toggle("on", x === a));
  const v = a.dataset.view;
  $$(".view").forEach((s) => s.classList.toggle("on", s.id === "v-" + v));
  if (v === "library") Library.load();
  if (v === "settings") Settings.load();
  if (v === "director") Director.load();
  if (v === "production") { Production.load(); Projects.load(); }
  if (v === "casting") Casting.load();
}));

/* ─────────────────────────────────────────────── 상태 표시 */

const Health = {
  async tick() {
    const box = $("#health");
    try {
      const s = await api("/api/status");
      const line = (name, ok, extra) =>
        `<div><b>${name}</b> <span class="${ok ? "ok" : "bad"}">${ok ? "●" : "●"}</span>` +
        (extra ? ` ${extra}` : "") + `</div>`;
      const vram = s.comfy.vram_free && s.comfy.vram_total
        ? `${(s.comfy.vram_free / 1073741824).toFixed(1)}/${(s.comfy.vram_total / 1073741824).toFixed(0)}GB`
        : "";
      box.innerHTML =
        line("ComfyUI", s.comfy.ok, vram) +
        line("Ollama", s.ollama.ok, s.ollama.ok ? `${(s.ollama.models || []).length}종` : "") +
        line("노드팩", s.pack.ok,
             s.pack.ok ? `${Object.values(s.pack.counts || {}).reduce((a, b) => a + b, 0)}개` : "");
      Health.last = s;
    } catch (e) {
      box.innerHTML = `<span class="bad">서버 연결 실패</span>`;
    }
  },
};

/* ─────────────────────────────────────────────── 라이브러리 */

const Library = {
  items: [], kind: "", q: "", sel: null, loaded: false,

  async load(force) {
    if (this.loaded && !force) { this.render(); return; }
    try {
      const d = await api("/api/library");
      this.items = d.items || [];
      this.root = d.root || "";
      this.kinds = d.kinds || [];
      this.loaded = true;
    } catch (e) {
      this.items = []; this.err = e.message;
    }
    this.render();
  },

  filtered() {
    const q = this.q.trim().toLowerCase();
    return this.items.filter((it) => {
      if (this.kind && it.kind !== this.kind) return false;
      if (!q) return true;
      return (it.name + " " + it.description + " " + (it.tags || []).join(" "))
        .toLowerCase().includes(q);
    });
  },

  render() {
    const counts = {};
    for (const it of this.items) counts[it.kind] = (counts[it.kind] || 0) + 1;
    const kb = $("#lib-kinds");
    kb.innerHTML = "";
    const mk = (k, label, n) => el("div", {
      class: "kind" + (this.kind === k ? " on" : ""),
      html: `${label}<span class="n">${n}</span>`,
      on: { click: () => { this.kind = k; this.render(); } },
    });
    kb.appendChild(mk("", "전체", this.items.length));
    for (const k of (this.kinds || Object.keys(KIND_KO)))
      kb.appendChild(mk(k, KIND_KO[k] || k, counts[k] || 0));

    const grid = $("#lib-grid");
    grid.innerHTML = "";
    const list = this.filtered();
    if (!list.length) {
      grid.appendChild(el("div", {
        class: "empty",
        html: this.err
          ? `읽지 못했습니다 — ${this.err}`
          : this.items.length
            ? "조건에 맞는 에셋이 없습니다."
            : `아직 에셋이 없습니다.<br><span class="muted">ComfyUI 의 📚 Asset Save 노드로 저장하면 여기 나타납니다.</span>`,
      }));
    }
    for (const it of list) {
      const c = el("div", {
        class: "card" + (this.sel?.id === it.id ? " on" : ""),
        on: { click: () => { this.sel = it; this.render(); } },
      });
      if (it.cover) {
        c.appendChild(el("img", { attr: {
          src: `/api/library/image?kind=${it.kind}&id=${it.id}`, loading: "lazy" } }));
      } else {
        c.appendChild(el("div", { class: "no", text: "이미지 없음" }));
      }
      c.appendChild(el("div", { class: "kd", text: KIND_KO[it.kind] || it.kind }));
      if (it.favorite) c.appendChild(el("div", { class: "fav", text: "★" }));
      c.appendChild(el("div", { class: "nm", text: it.name }));
      grid.appendChild(c);
    }

    const d = $("#lib-detail");
    d.innerHTML = "";
    if (!this.sel) {
      d.appendChild(el("p", { class: "muted", text: "에셋을 고르세요" }));
      return;
    }
    const it = this.sel;
    if (it.cover) {
      d.appendChild(el("img", { attr: {
        src: `/api/library/image?kind=${it.kind}&id=${it.id}` } }));
    }
    d.appendChild(el("h3", { text: it.name }));
    d.appendChild(el("div", { class: "k",
      text: `${KIND_KO[it.kind] || it.kind} · ${it.id}` }));
    d.appendChild(el("div", {
      class: it.description ? "desc" : "desc muted",
      text: it.description || "설명 없음 — <Subject N> 정의문이 비어 나갑니다",
    }));
    if ((it.tags || []).length) {
      const t = el("div", { class: "tags" });
      for (const g of it.tags) t.appendChild(el("span", { class: "tag", text: g }));
      d.appendChild(t);
    }
    d.appendChild(el("div", { class: "k", text: `파일: ${it.files.join(", ") || "—"}` }));
  },
};

$("#lib-q").addEventListener("input", (e) => { Library.q = e.target.value; Library.render(); });
$("#lib-reload").addEventListener("click", () => Library.load(true));

/* ─────────────────────────────────────────────── 설정 */

const Settings = {
  async load() {
    const c = await api("/api/config");
    $("#c-comfy").value = c.comfy_url || "";
    $("#c-ollama").value = c.ollama_url || "";
    $("#c-output").value = c.comfy_output || "";
    $("#c-temp").value = c.temperature ?? 0.7;
    $("#c-ctx").value = c.num_ctx ?? 16384;

    const s = Health.last || await api("/api/status");
    const sel = $("#c-model");
    sel.innerHTML = "";
    const models = s.ollama.models || [];
    if (!models.length) sel.appendChild(el("option", { text: "(Ollama 를 못 읽었습니다)" }));
    for (const m of models) sel.appendChild(el("option", { text: m, attr: { value: m } }));
    if (c.ollama_model) sel.value = c.ollama_model;

    const p = $("#probe");
    const row = (name, ok, txt) =>
      `<div class="line"><span class="name">${name}</span>` +
      `<span class="${ok ? "ok" : "bad"}">${ok ? "연결됨" : "실패"}</span>` +
      `<span class="muted">${txt || ""}</span></div>`;
    p.innerHTML =
      row("ComfyUI", s.comfy.ok, s.comfy.ok
        ? `${s.comfy.device || ""} · ComfyUI ${s.comfy.version || ""}`
        : s.comfy.error) +
      row("Ollama", s.ollama.ok, s.ollama.ok
        ? `모델 ${models.length}종` : s.ollama.error) +
      row("노드 팩", s.pack.ok, s.pack.ok
        ? s.pack.path : s.pack.error) +
      row("라이브러리", !!s.pack.exists,
        s.pack.library_root || "");
  },
};

$("#c-save").addEventListener("click", async () => {
  const msg = $("#c-msg");
  msg.textContent = "저장 중…";
  try {
    await api("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        comfy_url: $("#c-comfy").value.trim(),
        ollama_url: $("#c-ollama").value.trim(),
        ollama_model: $("#c-model").value,
        comfy_output: $("#c-output").value.trim(),
        temperature: parseFloat($("#c-temp").value),
        num_ctx: parseInt($("#c-ctx").value, 10),
      }),
    });
    msg.textContent = "저장했습니다";
    Library.loaded = false;
    await Health.tick();
    await Settings.load();
  } catch (e) {
    msg.textContent = "실패 — " + e.message;
  }
  setTimeout(() => { msg.textContent = ""; }, 2600);
});

/* ─────────────────────────────────────────────── 시작 */

// 디렉터에서 프롬프트가 나오면 프로덕션 칸에 바로 꽂아 둔다.
wireDirector((prompt) => Production.setPrompt(prompt));
wireProduction();
wireProjects();
// 에셋을 저장하면 라이브러리를 다시 읽는다.
wireCasting(() => { Library.loaded = false; });
wireRefs();
wireWorkflows();

Health.tick();
setInterval(() => Health.tick(), 15000);
Library.load();
