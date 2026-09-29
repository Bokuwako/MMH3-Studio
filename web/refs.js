// 레퍼런스 고르기 — 라이브러리에서 에셋을 골라 <Picture N> 순서를 정한다.
//
// 고른 순서가 그대로 Picture 번호가 된다. 그래서 목록이 아니라 '줄'로 보여주고,
// 위아래로 옮길 수 있게 한다 — 번호가 뒤바뀌면 프롬프트의 지시가 딴 그림을
// 가리키게 되고, 그건 눈으로 찾기 아주 어려운 종류의 실수다.

import { $, api, el, KIND_KO } from "/web/util.js";

// 종류로부터 역할을 추측한다. 사람이 바꿀 수 있고, 바꾸면 그게 이긴다.
const ROLE_GUESS = {
  actors: "character_full", scenes: "background", costumes: "outfit",
  props: "prop", layouts: "pose", voices: "",
};

export const Refs = {
  roles: [],
  picked: [],          // [{id, kind, name, description, file_key, cover}]
  all: [],
  open: false,

  async loadAll() {
    try {
      const d = await api("/api/library");
      this.all = d.items || [];
    } catch { this.all = []; }
    if (!this.roles.length) {
      try {
        const v = await api("/api/vocab");
        this.roles = (v.ref_role || []).filter((r) => r.key);
      } catch { /* 역할 목록이 없으면 추측값만 쓴다 */ }
    }
  },

  has(id) { return this.picked.some((p) => p.id === id); },

  add(it) {
    if (this.has(it.id)) return;
    this.picked.push({ id: it.id, kind: it.kind, name: it.name,
                       description: it.description, file_key: "",
                       role: ROLE_GUESS[it.kind] || "character", cover: it.cover });
    this.paint();
  },

  remove(i) { this.picked.splice(i, 1); this.paint(); },

  move(i, d) {
    const j = i + d;
    if (j < 0 || j >= this.picked.length) return;
    [this.picked[i], this.picked[j]] = [this.picked[j], this.picked[i]];
    this.paint();
  },

  /** 브리프에 들어갈 역할 선언. shotcards.build 가 refs 로 받는다. */
  briefRefs() {
    return this.picked.map((p, i) => ({ n: i + 1, role: p.role || "" }));
  },

  /** <Subject N> 정의문으로 쓸 인물 설명. */
  subjectsText() {
    const lines = [];
    this.picked.forEach((p, i) => {
      if (!p.description) return;
      lines.push(`<Picture ${i + 1}> (${p.name}): ${p.description}`);
    });
    return lines.join("\n");
  },

  paint() {
    const box = $("#r-list");
    if (!box) return;
    box.innerHTML = "";
    if (!this.picked.length) {
      box.appendChild(el("p", { class: "muted",
        text: "레퍼런스 없음 — T2VA 로 나갑니다." }));
    }
    this.picked.forEach((p, i) => {
      const row = el("div", { class: "refrow" }, [
        el("span", { class: "pn", text: `P${i + 1}` }),
        el("img", { attr: { src: `/api/library/image?kind=${p.kind}&id=${p.id}` } }),
        el("div", { class: "meta" }, [
          el("div", { class: "nm", text: p.name }),
          (() => {
            const s = el("select", { class: "rolesel",
              on: { change: (e) => { p.role = e.target.value; } } });
            const list = this.roles.length
              ? this.roles
              : [{ key: p.role, label: p.role }];
            for (const r of list)
              s.appendChild(el("option", { text: r.label, attr: { value: r.key } }));
            s.value = p.role || "";
            return s;
          })(),
        ]),
        el("button", { class: "x", text: "▲", on: { click: () => this.move(i, -1) } }),
        el("button", { class: "x", text: "▼", on: { click: () => this.move(i, 1) } }),
        el("button", { class: "x", text: "✕", on: { click: () => this.remove(i) } }),
      ]);
      box.appendChild(row);
    });
    const n = $("#r-count");
    if (n) n.textContent = this.picked.length ? String(this.picked.length) : "";
  },

  async pickerOpen() {
    await this.loadAll();
    const ov = el("div", { class: "ovl", on: { mousedown: (e) => {
      if (e.target === ov) ov.remove(); } } });
    const card = el("div", { class: "ovl-card" });
    card.appendChild(el("div", { class: "ovl-head" }, [
      el("b", { text: "레퍼런스 고르기" }),
      el("span", { class: "grow" }),
      el("button", { class: "btn", text: "닫기", on: { click: () => ov.remove() } }),
    ]));
    const grid = el("div", { class: "grid" });
    if (!this.all.length) {
      grid.appendChild(el("div", { class: "empty",
        text: "라이브러리가 비었습니다 — 캐스팅에서 먼저 만드세요." }));
    }
    for (const it of this.all) {
      const on = this.has(it.id);
      grid.appendChild(el("div", {
        class: "card" + (on ? " on" : ""),
        on: { click: () => {
          if (this.has(it.id)) {
            this.picked = this.picked.filter((p) => p.id !== it.id);
          } else this.add(it);
          this.paint();
          ov.remove();
          this.pickerOpen();
        } },
      }, [
        it.cover
          ? el("img", { attr: { src: `/api/library/image?kind=${it.kind}&id=${it.id}`,
                                loading: "lazy" } })
          : el("div", { class: "no", text: "이미지 없음" }),
        el("div", { class: "kd", text: KIND_KO[it.kind] || it.kind }),
        el("div", { class: "nm", text: (on ? "✓ " : "") + it.name }),
      ]));
    }
    card.appendChild(grid);
    ov.appendChild(card);
    document.body.appendChild(ov);
  },
};

export function wireRefs() {
  $("#r-add").addEventListener("click", () => Refs.pickerOpen());
  Refs.paint();
}
