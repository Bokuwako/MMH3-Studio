// 워크플로우 가져오기 — ComfyUI 에서 API 포맷으로 내보낸 그래프를 앱에 등록한다.
//
// 앱이 건드리는 건 binding 이 가리키는 몇 군데뿐이다. 모델·LoRA·최적화·업스케일은
// 그래프 것이고 그대로 실행된다. 그래서 자기 워크플로우를 통째로 넣어도 된다.

import { $, api, el } from "/web/util.js";

let pending = null;   // {graph, binding, name}

export async function paintWorkflows() {
  const box = $("#wf-list");
  if (!box) return;
  box.innerHTML = "";
  try {
    const d = await api("/api/workflows");
    for (const w of d.items || []) {
      box.appendChild(el("div", { class: "wfrow" }, [
        el("span", { class: "nm", text: w.name }),
        el("span", { class: w.bound ? "ok" : "bad",
                     text: w.bound ? "연결됨" : "binding 미완성" }),
        el("span", { class: "grow" }),
        el("button", {
          class: "btn dgr", text: "삭제",
          on: { click: async () => {
            await api("/api/workflows/delete", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: w.name }),
            });
            paintWorkflows();
          } },
        }),
      ]));
    }
    if (!(d.items || []).length) {
      box.appendChild(el("p", { class: "muted", text: "등록된 워크플로우가 없습니다." }));
    }
  } catch (e) {
    box.appendChild(el("p", { class: "muted", text: "목록 실패 — " + e.message }));
  }
}

export function wireWorkflows() {
  const rep = () => $("#wf-report");

  $("#wf-check").addEventListener("click", async () => {
    const r = rep();
    r.innerHTML = "";
    pending = null;
    $("#wf-save").disabled = true;
    let graph;
    try {
      graph = JSON.parse($("#wf-json").value);
    } catch (e) {
      r.innerHTML = `<div class="line"><span class="bad">JSON 을 읽지 못했습니다</span>` +
                    `<span class="muted">${e.message}</span></div>`;
      return;
    }
    try {
      const d = await api("/api/workflows/inspect", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ graph }),
      });
      const b = d.binding || {};
      const line = (k, v, good) =>
        `<div class="line"><span class="name">${k}</span>` +
        `<span class="${good ? "ok" : "bad"}">${v || "못 찾음"}</span></div>`;
      r.innerHTML =
        line("프롬프트", b.h3_node ? `노드 ${b.h3_node}.${b.prompt_input}` : "", !!b.prompt_input) +
        line("크기", b.width_input ? `${b.width_input}/${b.height_input}`
             : (b.size_node ? `노드 ${b.size_node}` : ""), !!(b.width_input || b.size_node)) +
        line("길이", b.frames_input, !!b.frames_input) +
        line("레퍼런스", b.picture_pattern, !!b.picture_pattern) +
        line("시드", b.seed_node ? `노드 ${b.seed_node}.${b.seed_input}` : "", !!b.seed_node) +
        line("출력", b.output_node ? `노드 ${b.output_node}` : "", !!b.output_node) +
        (d.notes || []).map((n) => `<div class="line"><span class="muted">· ${n}</span></div>`).join("");
      if (d.ok) {
        pending = { graph, binding: b };
        $("#wf-save").disabled = false;
      } else {
        r.innerHTML += `<div class="line"><span class="bad">필수 항목이 빠져서 가져올 수 없습니다</span></div>`;
      }
    } catch (e) {
      r.innerHTML = `<div class="line"><span class="bad">${e.message}</span></div>`;
    }
  });

  $("#wf-save").addEventListener("click", async () => {
    if (!pending) return;
    const name = $("#wf-name").value.trim();
    if (!name) { rep().innerHTML = `<div class="line"><span class="bad">이름을 적으세요</span></div>`; return; }
    try {
      const d = await api("/api/workflows/import", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, graph: pending.graph, binding: pending.binding }),
      });
      rep().innerHTML = `<div class="line"><span class="ok">가져왔습니다 — ${d.name}</span></div>`;
      $("#wf-json").value = "";
      pending = null;
      $("#wf-save").disabled = true;
      paintWorkflows();
    } catch (e) {
      rep().innerHTML = `<div class="line"><span class="bad">${e.message}</span></div>`;
    }
  });

  paintWorkflows();
}
