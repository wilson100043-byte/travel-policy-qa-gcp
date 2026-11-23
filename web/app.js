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

  function el(tag, className, textValue) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (textValue !== undefined) node.textContent = textValue;
    return node;
  }

  function scrollToLatest() {
    messages.scrollTop = messages.scrollHeight;
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
    sendButton.querySelector("span:first-child").textContent = value ? "查詢中" : "送出";
  }

  function renderUser(textValue) {
    const bubble = el("div", "message user", textValue);
    messages.append(bubble);
    scrollToLatest();
    return bubble;
  }

  function renderAnswer(answer, sources, mode) {
    const wrapper = el("article", "message assistant");
    wrapper.append(el("div", "assistant-avatar", "R"));
    const content = el("div", "answer-content");
    const heading = el("div", "answer-heading");
    heading.append(el("span", "", "規定助理"));
    if (mode === "offline" || mode === "local" || mode === "keyword") {
      heading.append(el("span", "mode-badge", "本機查詢"));
    }
    content.append(heading, el("div", "answer-text", answer));
    if (Array.isArray(sources) && sources.length) {
      const sourceList = el("div", "sources");
      sourceList.append(el("div", "sources-title", `參考來源 · ${sources.length}`));
      for (const source of sources) {
        const item = el("div", "source");
        const documentName = typeof source.document === "string" ? source.document : "未命名文件";
        const sectionName = typeof source.section === "string" ? source.section : "";
        item.append(el("strong", "", sectionName ? `${documentName} · ${sectionName}` : documentName));
        if (typeof source.excerpt === "string" && source.excerpt.trim()) {
          item.append(el("p", "", source.excerpt));
        }
        sourceList.append(item);
      }
      content.append(sourceList);
    }
    wrapper.append(content);
    messages.append(wrapper);
    scrollToLatest();
  }

  function recentHistory() {
    return turns.slice(-3).flatMap(({ question, answer }) => [
      { role: "user", content: question },
      { role: "assistant", content: answer },
    ]);
  }

  async function ask(rawQuestion) {
    const question = rawQuestion.trim();
    if (!question || busy) return;
    setError("");
    welcome.hidden = true;
    const userBubble = renderUser(question);
    const pending = el("div", "message assistant pending", "正在查詢文件並整理回答");
    messages.append(pending);
    scrollToLatest();
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
      pending.remove();
      renderAnswer(result.answer, result.sources, result.mode);
      turns.push({ question, answer: result.answer });
      questionInput.value = "";
    } catch (error) {
      pending.remove();
      userBubble.remove();
      if (!turns.length) welcome.hidden = false;
      setError(error.name === "AbortError" ? "查詢等候超過 45 秒，請稍後重試。" : error.message || "連線失敗，請確認本機服務已啟動。");
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
    setError("");
    questionInput.focus();
  });
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => ask(button.dataset.question));
  });
})();
