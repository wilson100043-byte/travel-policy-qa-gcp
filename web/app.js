(() => {
  "use strict";

  const form = document.querySelector("#question-form");
  const questionInput = document.querySelector("#question");
  const sendButton = document.querySelector("#send");
  const messages = document.querySelector("#messages");
  const errorBanner = document.querySelector("#error");
  const clearButton = document.querySelector("#clear-chat");
  const welcome = document.querySelector("#welcome");
  const turns = [];
  let busy = false;
  let requestController = null;

  // Amounts and deadlines quoted from the policy, e.g. 新臺幣 2,500 元, 30 個曆日, NT$300.
  const FIGURE = /(?:新臺幣\s*)?\d[\d,]*(?:\.\d+)?\s*(?:個曆日|個工作天|個工作日|元|天|日|%)|NT\$\s*\d[\d,]*/g;

  function el(tag, className, textValue) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (textValue !== undefined) node.textContent = textValue;
    return node;
  }

  // Build text with highlighted figures using text nodes only (no HTML parsing).
  function withFigures(tag, className, textValue) {
    const node = el(tag, className);
    let last = 0;
    for (const match of textValue.matchAll(FIGURE)) {
      if (match.index > last) node.append(textValue.slice(last, match.index));
      node.append(el("span", "figure", match[0]));
      last = match.index + match[0].length;
    }
    if (last < textValue.length) node.append(textValue.slice(last));
    return node;
  }

  function scrollToLatest(node) {
    node.scrollIntoView({ block: "end", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  function setError(message) {
    errorBanner.textContent = message;
    errorBanner.hidden = !message;
  }

  function setBusy(value) {
    busy = value;
    sendButton.disabled = value;
    questionInput.disabled = value;
    clearButton.disabled = value;
    sendButton.querySelector("span").textContent = value ? "查詢中" : "送出";
  }

  function row(kind, markText) {
    const node = el("div", `row ${kind}`);
    node.append(el("span", "mark", markText));
    return node;
  }

  function renderQuestion(textValue) {
    const entry = el("article", "entry");
    const q = row("q", "問");
    q.append(el("p", "q-text", textValue));
    const a = row("a", "答");
    const body = el("div", "a-body");
    body.append(el("p", "pending", "正在查詢規定"));
    a.append(body);
    entry.append(q, a);
    messages.append(entry);
    scrollToLatest(entry);
    return { entry, body };
  }

  function renderAnswer(body, answer, sources, mode) {
    body.replaceChildren();
    const meta = el("div", "a-meta");
    meta.append(el("span", "mode-badge", mode === "vertex" ? "AI 整理" : "原文摘錄"));
    body.append(meta, withFigures("p", "a-text", answer));

    if (Array.isArray(sources) && sources.length) {
      const stubs = el("div", "stubs");
      sources.forEach((source, index) => {
        const stub = el("section", "stub");
        const head = el("div", "stub-head");
        head.append(el("span", "", `依據 ${index + 1} / ${sources.length}`));
        stub.append(head);
        stub.append(el("p", "stub-doc", typeof source.document === "string" ? source.document : "未命名文件"));
        if (typeof source.section === "string" && source.section) stub.append(el("p", "stub-section", source.section));
        if (typeof source.excerpt === "string" && source.excerpt.trim()) {
          stub.append(withFigures("p", "stub-excerpt", source.excerpt.trim() + "…"));
          const toggle = el("button", "stub-toggle", "顯示全文");
          toggle.type = "button";
          toggle.setAttribute("aria-expanded", "false");
          toggle.addEventListener("click", () => {
            const expanded = stub.classList.toggle("expanded");
            toggle.textContent = expanded ? "收合" : "顯示全文";
            toggle.setAttribute("aria-expanded", String(expanded));
          });
          stub.append(toggle);
        }
        const stamp = el("span", "stamp", "現行");
        stamp.setAttribute("aria-label", "目前生效的規定");
        stub.append(stamp);
        stubs.append(stub);
      });
      body.append(stubs);
    }
  }

  function recentHistory() {
    return turns.slice(-3).flatMap(({ question, answer }) => [
      { role: "user", content: question },
      { role: "assistant", content: answer },
    ]);
  }

  function resizeInput() {
    questionInput.style.height = "auto";
    questionInput.style.height = Math.min(questionInput.scrollHeight, 140) + "px";
  }

  async function ask(rawQuestion) {
    const question = rawQuestion.trim();
    if (!question || busy) return;
    setError("");
    welcome.hidden = true;
    const { entry, body } = renderQuestion(question);
    setBusy(true);
    requestController = new AbortController();
    const timeoutId = setTimeout(() => requestController.abort(), 45000);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history: recentHistory() }),
        signal: requestController.signal,
      });
      let result;
      try { result = await response.json(); } catch { result = null; }
      if (!response.ok) {
        const detail = result && typeof result.detail === "string" ? result.detail : "目前無法取得回答，請稍後重試。";
        throw new Error(detail);
      }
      if (!result || typeof result.answer !== "string") throw new Error("伺服器回傳格式不正確，請稍後重試。");
      renderAnswer(body, result.answer, result.sources, result.mode);
      turns.push({ question, answer: result.answer });
      questionInput.value = "";
      resizeInput();
      scrollToLatest(entry);
    } catch (error) {
      entry.remove();
      if (!turns.length) welcome.hidden = false;
      setError(error.name === "AbortError" ? "查詢超過 45 秒沒有回應，請稍後重試。" : error.message || "連線失敗，請確認服務已啟動。");
    } finally {
      clearTimeout(timeoutId);
      requestController = null;
      setBusy(false);
      questionInput.focus();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    ask(questionInput.value);
  });
  questionInput.addEventListener("input", resizeInput);
  questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  clearButton.addEventListener("click", () => {
    turns.length = 0;
    messages.replaceChildren(welcome);
    welcome.hidden = false;
    questionInput.value = "";
    resizeInput();
    setError("");
    questionInput.focus();
  });
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => ask(button.dataset.question));
  });
})();
