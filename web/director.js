// 디렉터 화면 — 샷 카드를 브리프로, 브리프를 프롬프트로.
// 조립과 검증은 전부 서버(=팩의 mmh3)가 한다. 여기서는 입력만 모은다.

import { $, $$, api, el } from "/web/util.js";
import { Refs } from "/web/refs.js";

export const Director = {
  vocab: null,
  lastBrief: "",
  lastPrompt: "",
  models: [],
  set: {
    mode: "T2VA", style: "", theme: "", lens: "", depth_of_field: "",
    lighting: "", duration: 5, dialogue_language: "Korean",
    dialogue_mode: "auto", subjects: "", model: "",
  },
  cards: [],

  async load() {
    if (this.vocab) return;
    try {
      this.vocab = await api("/api/vocab");
    } catch (e) {
      $("#d-settings").innerHTML =
        `<p class="muted">어휘를 읽지 못했습니다 — ${e.message}</p>`;
      return;
    }
    // 모델은 설정에 저장된 것을 쓰되, 없으면 Ollama 가 가진 첫 번째를 쓴다.
    // 설정 화면까지 가서 한 번 저장해야만 쓸 수 있는 건 불편하다.
    try {
      const [st, cfg] = await Promise.all([api("/api/status"), api("/api/config")]);
      this.models = (st.ollama && st.ollama.models) || [];
      this.set.model = cfg.ollama_model || this.models[0] || "";
    } catch { /* 상태를 못 읽어도 화면은 뜬다 */ }
    const v = this.vocab, f = (a) => (a && a.length ? a[0] : "");
    Object.assign(this.set, {
      style: f(v.style), theme: f(v.theme), lens: f(v.lens),
      depth_of_field: f(v.depth_of_field), lighting: f(v.lighting),
    });
    if (!this.cards.length) this.addCard();
    this.renderSettings();
    this.renderCards();
  },

  /* ---- 전체 설정 ---- */
  renderSettings() {
    const v = this.vocab, box = $("#d-settings");
    box.innerHTML = "";
    const add = (label, node) => box.appendChild(el("label", { text: label }, [node]));
    const drop = (key, opts, labels) => {
      const s = el("select", { on: { change: (e) => { this.set[key] = e.target.value; } } });
      (opts || []).forEach((o, i) => s.appendChild(
        el("option", { text: labels ? labels[i] : o, attr: { value: o } })));
      s.value = this.set[key] || (opts && opts[0]) || "";
      return s;
    };
    const line = (key, attrs) => {
      const n = el("input", { attr: attrs,
        on: { input: (e) => { this.set[key] = attrs.type === "number"
          ? (parseFloat(e.target.value) || 0) : e.target.value; } } });
      n.value = this.set[key];
      return n;
    };

    add("Ollama 모델", drop("model", this.models.length ? this.models : [""],
                          this.models.length ? null : ["(Ollama 를 못 읽었습니다)"]));
    add("모드", drop("mode", ["T2VA", "REF2VA", "FL2VA"]));
    add("스타일", drop("style", v.style));
    add("테마 (장르)", drop("theme", v.theme));
    add("렌즈", drop("lens", v.lens));
    add("심도", drop("depth_of_field", v.depth_of_field));
    add("조명", drop("lighting", v.lighting));
    add("길이 (초)", line("duration", { type: "number", min: "1", max: "60", step: "1" }));
    add("대사 언어", line("dialogue_language", { type: "text" }));
    add("대사", drop("dialogue_mode", ["auto", "none", "speech"],
                     ["자동 판단", "대사 없음", "대사 있음"]));

    const subj = el("textarea", {
      attr: { rows: "3", placeholder: "인물 정의 (선택)" },
      on: { input: (e) => { this.set.subjects = e.target.value; } } });
    subj.value = this.set.subjects;
    add("인물", subj);
  },

  /* ---- 샷 카드 ---- */
  addCard() {
    const v = this.vocab || {}, f = (a) => (a && a.length ? a[0] : "");
    this.cards.push({
      at: "", text: "", extra: "",
      viewpoint: f(v.viewpoint), size: f(v.size), shot_type: f(v.shot_type),
      angle: f(v.angle), facing: f(v.facing), motion: f(v.motion),
      speed: f(v.speed), transition: f(v.transition),
    });
  },

  renderCards() {
    const v = this.vocab, list = $("#d-list");
    list.innerHTML = "";
    this.cards.forEach((c, i) => {
      const box = el("div", { class: "shot" });
      const hd = el("div", { class: "hd" }, [
        el("b", { text: `샷 ${i + 1}` }), el("span", { class: "grow" }),
      ]);
      if (this.cards.length > 1) {
        hd.appendChild(el("button", {
          class: "x", text: "✕",
          on: { click: () => { this.cards.splice(i, 1); this.renderCards(); } },
        }));
      }
      box.appendChild(hd);

      const field = (key, ph, tag, minH) => {
        const n = el(tag || "input", {
          attr: tag === "textarea" ? { placeholder: ph }
                                   : { type: "text", placeholder: ph },
          on: { input: (e) => { c[key] = e.target.value; } },
        });
        n.value = c[key] || "";
        if (minH) n.style.minHeight = minH;
        n.style.marginTop = "8px";
        return n;
      };
      const at = field("at", "장소 · 시간   예: 온천 노천탕, 해질 무렵");
      at.style.marginTop = "0";
      box.appendChild(at);
      box.appendChild(field("text", "내용 — 무슨 일이 일어나는지 자연어로", "textarea"));
      box.appendChild(field("extra", "추가 동작 (선택)", "textarea", "38px"));

      const g = el("div", { class: "g" });
      for (const [key, opts] of [
        ["viewpoint", v.viewpoint], ["size", v.size], ["shot_type", v.shot_type],
        ["angle", v.angle], ["facing", v.facing], ["motion", v.motion],
        ["speed", v.speed], ["transition", v.transition],
      ]) {
        const s = el("select", { on: { change: (e) => { c[key] = e.target.value; } } });
        for (const o of opts || []) s.appendChild(el("option", { text: o, attr: { value: o } }));
        s.value = c[key] || (opts && opts[0]) || "";
        g.appendChild(s);
      }
      box.appendChild(g);
      list.appendChild(box);
    });
  },

  /* ---- 서버 호출 ---- */
  async buildBrief() {
    const d = await api("/api/brief", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cards: this.cards,
        // 고른 에셋의 영어 설명이 <Subject N> 정의문이 된다. 사람이 적은
        // 인물 칸이 있으면 그 뒤에 붙인다.
        subjects: [this.set.subjects, Refs.subjectsText()]
          .filter(Boolean).join("\n"),
        refs: Refs.briefRefs(),
        theme: this.set.theme,
        duration: this.set.duration,
        dialogue_language: this.set.dialogue_language,
      }),
    });
    this.lastBrief = d.brief || "";
    $("#o-brief").textContent = this.lastBrief;
    return d;
  },

  async makePrompt() {
    // 레퍼런스를 골랐으면 REF2VA 다. 모드를 손으로 맞추게 두면 반드시 잊는다.
    if (Refs.picked.length && this.set.mode === "T2VA") {
      this.set.mode = "REF2VA";
      this.renderSettings();
    }
    const b = await this.buildBrief();
    const d = await api("/api/prompt", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        brief: b.brief, model: this.set.model,
        mode: this.set.mode, duration: this.set.duration,
        style: this.set.style, dialogue_mode: this.set.dialogue_mode,
        dialogue_language: this.set.dialogue_language,
        shot_count: this.cards.length,
        n_images: Refs.picked.length,
      }),
    });
    this.lastPrompt = d.prompt || "";
    return d;
  },
};

/* ---- 화면 배선 ---- */

function showTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
  for (const id of ["prompt", "brief", "report"])
    $("#o-" + id).classList.toggle("on", id === name);
}

export function wireDirector(onPrompt) {
  $$(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));

  $("#d-add").addEventListener("click", () => {
    Director.addCard(); Director.renderCards();
  });

  $("#d-brief").addEventListener("click", async () => {
    const m = $("#d-msg");
    m.textContent = "조립 중…";
    try { await Director.buildBrief(); showTab("brief"); m.textContent = ""; }
    catch (e) { m.textContent = "실패 — " + e.message; }
  });

  $("#d-run").addEventListener("click", async () => {
    const m = $("#d-msg"), btn = $("#d-run");
    btn.disabled = true;
    m.textContent = "브리프 조립…";
    const t0 = Date.now();
    try {
      m.textContent = "Ollama 가 쓰는 중… 수십 초 걸립니다";
      const d = await Director.makePrompt();
      $("#o-prompt").textContent = d.prompt || "";

      const rep = d.report || [];
      $("#d-nrep").textContent = rep.length ? String(rep.length) : "";
      const r = $("#o-report");
      r.innerHTML = "";
      if (!rep.length) {
        r.appendChild(el("div", { class: "ok-note", text: "문제 없음" }));
      }
      for (const it of rep) {
        r.appendChild(el("div", { class: "issue" }, [
          el("div", { class: "w", text: it.where }),
          el("div", { text: it.text }),
        ]));
      }
      showTab("prompt");
      m.textContent = `${((Date.now() - t0) / 1000).toFixed(0)}초 · ` +
                      `${(d.prompt || "").length}자` +
                      (rep.length ? ` · 검증 ${rep.length}건` : "");
      onPrompt?.(d.prompt || "");
    } catch (e) {
      m.textContent = "실패 — " + e.message;
    }
    btn.disabled = false;
  });
}
