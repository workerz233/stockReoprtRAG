(function (root, factory) {
  const api = factory();

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }

  root.chatComposerState = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  function getChatComposerState(state = {}, query = "") {
    const hasActiveProject = Boolean(state.activeProject);
    const isSendingMessage = Boolean(state.isSendingMessage);
    const hasQuery = Boolean(String(query || "").trim());

    if (isSendingMessage) {
      return {
        inputDisabled: true,
        buttonDisabled: true,
        buttonText: "发送中...",
        placeholder: "正在生成回答，请稍候...",
      };
    }

    if (!hasActiveProject) {
      return {
        inputDisabled: false,
        buttonDisabled: true,
        buttonText: "发送",
        placeholder: "请先选择左侧项目，再输入问题",
      };
    }

    return {
      inputDisabled: false,
      buttonDisabled: !hasQuery,
      buttonText: "发送",
      placeholder: "请输入问题，系统会只基于当前项目中的研报内容回答",
    };
  }

  function syncChatComposerState(state, elements) {
    const chatInputEl = elements?.chatInputEl;
    const sendChatBtnEl = elements?.sendChatBtnEl;
    const nextState = getChatComposerState(state, chatInputEl?.value || "");

    if (chatInputEl) {
      chatInputEl.disabled = nextState.inputDisabled;
      chatInputEl.placeholder = nextState.placeholder;
    }

    if (sendChatBtnEl) {
      sendChatBtnEl.disabled = nextState.buttonDisabled;
      sendChatBtnEl.textContent = nextState.buttonText;
    }

    return nextState;
  }

  return {
    getChatComposerState,
    syncChatComposerState,
  };
});
