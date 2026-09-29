// 프로덕션 — 프롬프트를 ComfyUI 로 보내고 결과 영상을 받는다.

import { $, api, el } from "/web/util.js";
import { Refs } from "/web/refs.js";

export const Production = {
  prompt: "",
  pid: null,
  timer: null,
  t0: 0,

  setPrompt(p) {
    this.prompt = p || "";
    const box = $("#p-prompt");
    if (box) box.value = this.prompt;
    this.updateReady();
  },

  updateReady() {
    const has = !!($("#p-prompt")?.value || "").trim();
    $("#p-go").disabled = !has || !!this.pid;
  },

  async load() {
    try {
      const d = await api("/api/workflows");
      const sel = $("#p-wf");
      const cur = sel.value;
      sel.innerHTML = "";
      for (const w of d.items || []) {
        sel.appendChild(el("option", {
          text: w.name + (w.bound ? "" : "  (연결 안 됨)"),
          attr: { value: w.name },
        }));
      }
      if (cur) sel.value = cur;
      if (!d.items?.length) {
        sel.appendChild(el("option", { text: "(workflows 폴더가 비었습니다)" }));
      }
    } catch (e) {
      $("#p-msg").textContent = "워크플로우 목록 실패 — " + e.message;
    }
    this.updateReady();
  },

  async start() {
    const msg = $("#p-msg");
    this.prompt = $("#p-prompt").value.trim();
    if (!this.prompt) { msg.textContent = "프롬프트가 비었습니다"; return; }

    msg.textContent = "큐에 넣는 중…";
    $("#p-go").disabled = true;
    try {
      // 디렉터에서 고른 레퍼런스를 ComfyUI 의 input 으로 먼저 올린다.
      // 순서가 곧 <Picture N> 번호라 고른 순서를 그대로 지킨다.
      let images = [];
      if (Refs.picked.length) {
        msg.textContent = `레퍼런스 ${Refs.picked.length}장 올리는 중…`;
        const up = await api("/api/refs/upload", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ assets: Refs.picked.map((p) => ({
            kind: p.kind, id: p.id, file_key: p.file_key })) }),
        });
        images = (up.refs || []).map((r) => r.comfy_name);
      }
      const d = await api("/api/render", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: this.prompt,
          workflow: $("#p-wf").value,
          duration: parseFloat($("#p-dur").value) || 5,
          width: parseInt($("#p-w").value, 10) || 1344,
          height: parseInt($("#p-h").value, 10) || 768,
          seed: parseInt($("#p-seed").value, 10) || 0,
          images,
        }),
      });
      this.pid = d.prompt_id;
      this.t0 = Date.now();
      $("#p-stop").disabled = false;
      msg.textContent = `큐 등록됨 · ${d.frames}프레임 · ${d.prompt_id.slice(0, 8)}`;
      this.poll();
    } catch (e) {
      msg.textContent = "실패 — " + e.message;
      $("#p-go").disabled = false;
    }
  },

  poll() {
    clearTimeout(this.timer);
    this.timer = setTimeout(async () => {
      if (!this.pid) return;
      const msg = $("#p-msg");
      try {
        const s = await api("/api/render/state?id=" + encodeURIComponent(this.pid));
        const secs = ((Date.now() - this.t0) / 1000).toFixed(0);
        if (!s.done) {
          msg.textContent = `렌더 중… ${secs}초` +
            (s.pending ? ` · 대기 ${s.pending}` : "");
          this.poll();
          return;
        }
        this.finish(s, secs);
      } catch (e) {
        msg.textContent = "상태 확인 실패 — " + e.message;
        this.poll();
      }
    }, 2000);
  },

  finish(s, secs) {
    this.pid = null;
    $("#p-stop").disabled = true;
    this.updateReady();
    const msg = $("#p-msg"), out = $("#p-out");
    if (s.failed) { msg.textContent = "실패 — " + (s.error || ""); return; }
    msg.textContent = `완료 · ${secs}초`;
    out.innerHTML = "";
    for (const o of s.outputs || []) {
      const isVid = /\.(mp4|webm|mov|mkv)$/i.test(o.filename);
      const isImg = /\.(png|jpe?g|webp|gif)$/i.test(o.filename);
      const wrap = el("div", { class: "result" });
      if (isVid) {
        const v = el("video", { attr: { src: o.url, controls: "", loop: "" } });
        wrap.appendChild(v);
      } else if (isImg) {
        wrap.appendChild(el("img", { attr: { src: o.url } }));
      }
      wrap.appendChild(el("div", { class: "cap" }, [
        el("span", { text: o.filename }),
        el("a", { text: "열기", attr: { href: o.url, target: "_blank" } }),
      ]));
      out.appendChild(wrap);
    }
    if (!(s.outputs || []).length) {
      out.appendChild(el("p", { class: "muted",
        text: "산출물이 없습니다 — 워크플로우에 SaveVideo/SaveImage 가 있는지 보세요." }));
    }
  },

  async stop() {
    try { await api("/api/render/cancel", { method: "POST" }); } catch {}
    $("#p-msg").textContent = "중단 요청함";
  },
};

export function wireProduction() {
  $("#p-go").addEventListener("click", () => Production.start());
  $("#p-stop").addEventListener("click", () => Production.stop());
  $("#p-prompt").addEventListener("input", () => Production.updateReady());
  $("#p-seed-r").addEventListener("click", () => {
    $("#p-seed").value = Math.floor(Math.random() * 2 ** 31);
  });
}

/* ── 프로젝트 (ComfyUI 의 H3 Project Suite 를 그대로 부린다) ── */

export const Projects = {
  async load() {
    const sel = $("#p-proj"), st = $("#p-projstate");
    if (!sel) return;
    try {
      const d = await api("/api/projects");
      if (!d.installed) {
        st.textContent = "H3 Project Suite 없음";
        sel.innerHTML = "";
        sel.appendChild(el("option", { text: "(미설치)" }));
        return;
      }
      const names = (d.data && d.data.projects) || [];
      const cur = sel.value;
      sel.innerHTML = "";
      sel.appendChild(el("option", { text: "(안 씀)", attr: { value: "" } }));
      for (const n of names) sel.appendChild(el("option", { text: n, attr: { value: n } }));
      if (cur) sel.value = cur;
      this.refresh();
    } catch (e) {
      st.textContent = "목록 실패";
    }
  },

  async refresh() {
    const name = $("#p-proj")?.value, st = $("#p-projstate");
    if (!name) { st.textContent = ""; return; }
    try {
      const s = await api("/api/project/state?name=" + encodeURIComponent(name));
      const approved = (s.clips || []).filter((c) => c.status === "approved").length;
      st.textContent = `승인 ${approved}` +
        (s.pending ? ` · 클립 ${s.pending.index} 대기` : "") +
        (s.chain_active ? " · 체인 켜짐" : "");
    } catch (e) {
      st.textContent = "상태 실패";
    }
  },

  async approve() {
    const name = $("#p-proj")?.value;
    if (!name) return;
    try {
      await api("/api/project/act", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "approve", body: { name } }),
      });
      $("#p-msg").textContent = "승인함";
      this.refresh();
    } catch (e) {
      $("#p-msg").textContent = "승인 실패 — " + e.message;
    }
  },
};

export function wireProjects() {
  $("#p-proj")?.addEventListener("change", () => Projects.refresh());
  $("#p-approve")?.addEventListener("click", () => Projects.approve());
}
