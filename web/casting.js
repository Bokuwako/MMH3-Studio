// 캐스팅 — 배우·장소·소품 그림을 뽑아서 라이브러리에 굳힌다.
//
// 흐름은 한 줄이다: 프롬프트 → 렌더 → 마음에 드는 것 고르기 → 에셋으로 저장.
// 저장하고 나면 디렉터의 <Picture N> 과 <Subject N> 이 그걸 쓴다.

import { $, api, el, KIND_KO } from "/web/util.js";

export const Casting = {
  pid: null,
  timer: null,
  t0: 0,
  results: [],
  picked: new Set(),

  async load() {
    try {
      const d = await api("/api/workflows");
      const sel = $("#k-wf");
      const cur = sel.value;
      sel.innerHTML = "";
      for (const w of d.items || []) {
        sel.appendChild(el("option", { text: w.name, attr: { value: w.name } }));
      }
      // 이미지용 워크플로우가 있으면 그걸 기본으로.
      const img = (d.items || []).find((w) => /image/i.test(w.name));
      sel.value = cur || (img ? img.name : sel.value);
    } catch (e) {
      $("#k-msg").textContent = "워크플로우 목록 실패 — " + e.message;
    }
    const kd = $("#k-kind");
    if (!kd.options.length) {
      for (const [k, ko] of Object.entries(KIND_KO)) {
        if (k === "voices") continue;
        kd.appendChild(el("option", { text: ko, attr: { value: k } }));
      }
    }
  },

  async start() {
    const msg = $("#k-msg");
    const prompt = $("#k-prompt").value.trim();
    if (!prompt) { msg.textContent = "프롬프트가 비었습니다"; return; }
    $("#k-go").disabled = true;
    msg.textContent = "큐에 넣는 중…";
    this.results = []; this.picked.clear(); this.paint();
    try {
      const d = await api("/api/render", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          negative: $("#k-neg").value.trim(),
          workflow: $("#k-wf").value,
          width: parseInt($("#k-w").value, 10) || 1024,
          height: parseInt($("#k-h").value, 10) || 1024,
          batch: parseInt($("#k-batch").value, 10) || 1,
          seed: parseInt($("#k-seed").value, 10) || 0,
        }),
      });
      this.pid = d.prompt_id; this.t0 = Date.now();
      msg.textContent = "생성 중…";
      this.poll();
    } catch (e) {
      msg.textContent = "실패 — " + e.message;
      $("#k-go").disabled = false;
    }
  },

  poll() {
    clearTimeout(this.timer);
    this.timer = setTimeout(async () => {
      if (!this.pid) return;
      const msg = $("#k-msg");
      try {
        const s = await api("/api/render/state?id=" + encodeURIComponent(this.pid));
        const secs = ((Date.now() - this.t0) / 1000).toFixed(0);
        if (!s.done) { msg.textContent = `생성 중… ${secs}초`; this.poll(); return; }
        this.pid = null;
        $("#k-go").disabled = false;
        if (s.failed) { msg.textContent = "실패 — " + (s.error || ""); return; }
        this.results = (s.outputs || []).filter(
          (o) => /\.(png|jpe?g|webp)$/i.test(o.filename));
        this.picked = new Set(this.results.map((_, i) => i));
        msg.textContent = `${secs}초 · ${this.results.length}장`;
        this.paint();
      } catch (e) {
        msg.textContent = "상태 확인 실패 — " + e.message;
        this.poll();
      }
    }, 1500);
  },

  paint() {
    const box = $("#k-out");
    box.innerHTML = "";
    if (!this.results.length) {
      box.appendChild(el("p", { class: "muted", text: "생성 결과가 여기 나옵니다." }));
      $("#k-save").disabled = true;
      return;
    }
    for (let i = 0; i < this.results.length; i++) {
      const o = this.results[i];
      const on = this.picked.has(i);
      const c = el("div", {
        class: "card" + (on ? " on" : ""),
        on: { click: () => {
          if (this.picked.has(i)) this.picked.delete(i); else this.picked.add(i);
          this.paint();
        } },
      }, [
        el("img", { attr: { src: o.url, loading: "lazy" } }),
        el("div", { class: "nm", text: (on ? "✓ " : "") + o.filename }),
      ]);
      box.appendChild(c);
    }
    $("#k-save").disabled = !this.picked.size;
  },

  async save() {
    const msg = $("#k-msg"), btn = $("#k-save");
    const name = $("#k-name").value.trim();
    if (!name) { msg.textContent = "에셋 이름을 적으세요"; return; }
    btn.disabled = true;
    msg.textContent = "저장 중…";
    try {
      const files = [...this.picked].sort((a, b) => a - b).map((i) => this.results[i]);
      const d = await api("/api/library/save", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: $("#k-kind").value, name,
          file_key: $("#k-key").value.trim() || "master",
          description: $("#k-desc").value.trim(),
          tags: $("#k-tags").value.trim(),
          always_new: $("#k-new").checked,
          files,
        }),
      });
      msg.textContent = (d.created ? "새 에셋 " : "기존 에셋에 추가 ") +
                        d.id + " · " + d.files.join(", ");
    } catch (e) {
      msg.textContent = "저장 실패 — " + e.message;
    }
    btn.disabled = false;
  },
};

export function wireCasting(onSaved) {
  $("#k-go").addEventListener("click", () => Casting.start());
  $("#k-save").addEventListener("click", async () => {
    await Casting.save();
    onSaved?.();
  });
  $("#k-seed-r").addEventListener("click", () => {
    $("#k-seed").value = Math.floor(Math.random() * 2 ** 31);
  });
}
