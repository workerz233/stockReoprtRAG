const test = require("node:test");
const assert = require("node:assert/strict");

const {
  syncChatComposerState,
} = require("../frontend/chat-composer.js");

function createElements({ query = "", buttonDisabled = false } = {}) {
  return {
    chatInputEl: {
      value: query,
      disabled: false,
      placeholder: "",
    },
    sendChatBtnEl: {
      disabled: buttonDisabled,
      textContent: "发送",
    },
  };
}

test("enables send button when a project is active and the query has content", () => {
  const elements = createElements({ query: "宁德时代的 EPS 是多少？", buttonDisabled: true });

  syncChatComposerState(
    {
      activeProject: "catl",
      isSendingMessage: false,
    },
    elements
  );

  assert.equal(elements.sendChatBtnEl.disabled, false);
  assert.equal(elements.chatInputEl.disabled, false);
  assert.equal(elements.sendChatBtnEl.textContent, "发送");
});

test("keeps send button disabled while sending", () => {
  const elements = createElements({ query: "继续总结", buttonDisabled: false });

  syncChatComposerState(
    {
      activeProject: "catl",
      isSendingMessage: true,
    },
    elements
  );

  assert.equal(elements.sendChatBtnEl.disabled, true);
  assert.equal(elements.chatInputEl.disabled, true);
  assert.equal(elements.sendChatBtnEl.textContent, "发送中...");
});

test("disables send button when no project is selected", () => {
  const elements = createElements({ query: "可以回答吗？", buttonDisabled: false });

  syncChatComposerState(
    {
      activeProject: null,
      isSendingMessage: false,
    },
    elements
  );

  assert.equal(elements.sendChatBtnEl.disabled, true);
  assert.equal(elements.chatInputEl.disabled, false);
});
