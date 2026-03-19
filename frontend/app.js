const state = {
  activeProject: null,
  activeConversationId: null,
  projects: [],
  projectDocuments: {},
  projectConversations: {},
  conversationDetails: {},
  deletingProjects: {},
  deletingDocuments: {},
  deletingConversations: {},
  uploadPanelHidden: false,
  isSendingMessage: false,
};

const appShellEl = document.querySelector(".app-shell");
const projectListEl = document.getElementById("projectList");
const projectNameInputEl = document.getElementById("projectNameInput");
const createProjectBtnEl = document.getElementById("createProjectBtn");
const activeProjectNameEl = document.getElementById("activeProjectName");
const projectStatusEl = document.getElementById("projectStatus");
const uploadPanelEl = document.getElementById("uploadPanel");
const toggleUploadPanelBtnEl = document.getElementById("toggleUploadPanelBtn");
const hideUploadPanelBtnEl = document.getElementById("hideUploadPanelBtn");
const uploadStatusEl = document.getElementById("uploadStatus");
const pdfInputEl = document.getElementById("pdfInput");
const uploadPdfBtnEl = document.getElementById("uploadPdfBtn");
const conversationListEl = document.getElementById("conversationList");
const newConversationBtnEl = document.getElementById("newConversationBtn");
const chatMessagesEl = document.getElementById("chatMessages");
const chatInputEl = document.getElementById("chatInput");
const sendChatBtnEl = document.getElementById("sendChatBtn");
const syncComposerState =
  window.chatComposerState?.syncChatComposerState ||
  ((currentState, elements) => {
    const query = String(elements.chatInputEl?.value || "").trim();
    const hasActiveProject = Boolean(currentState.activeProject);
    const isSendingMessage = Boolean(currentState.isSendingMessage);

    elements.chatInputEl.disabled = isSendingMessage;
    elements.sendChatBtnEl.disabled = isSendingMessage || !hasActiveProject || !query;
    elements.sendChatBtnEl.textContent = isSendingMessage ? "发送中..." : "发送";
  });
const consumeSseStream =
  window.chatSse?.consumeSseStream ||
  (async () => {
    throw new Error("SSE helper 未加载");
  });

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderChatComposer() {
  syncComposerState(state, { chatInputEl, sendChatBtnEl });
}

function renderUploadPanelVisibility() {
  appShellEl.classList.toggle("upload-panel-hidden", state.uploadPanelHidden);
  uploadPanelEl.setAttribute("aria-hidden", String(state.uploadPanelHidden));
  toggleUploadPanelBtnEl.textContent = state.uploadPanelHidden ? "显示上传栏" : "隐藏上传栏";
}

function conversationKey(projectName, conversationId) {
  return `${projectName}::${conversationId}`;
}

function getDefaultChatHint() {
  if (!state.activeProject) {
    return "选择项目后即可提问，例如“宁德时代未来三年的 EPS 预测是多少？”";
  }
  return "点击“新建对话”或直接发送问题，系统会自动保存历史记录。";
}

function renderConversationMessages(messages = []) {
  chatMessagesEl.innerHTML = "";

  if (!messages.length) {
    appendMessage("assistant", getDefaultChatHint());
    return;
  }

  messages.forEach((message) => {
    appendMessage(message.role, message.content, message.sources || []);
  });
}

function renderSourcesHtml(sources = []) {
  if (!sources.length) {
    return "";
  }

  return `<div class="sources">${sources
    .slice(0, 5)
    .map((source) => {
      const pageLabel = source.page_no ? `第 ${source.page_no} 页` : "页码未知";
      const scoreLabel = Number.isFinite(source.score)
        ? ` · score ${Number(source.score).toFixed(4)}`
        : "";
      return `<div class="source-item"><strong>${escapeHtml(source.report_name)}</strong> · ${escapeHtml(source.section_path || "未命名章节")} · ${pageLabel}${scoreLabel}</div>`;
    })
    .join("")}</div>`;
}

function renderMessageBubble(role, text, options = {}) {
  const { markdown = role === "assistant", streaming = false } = options;

  if (role === "assistant" && markdown) {
    const renderMarkdown =
      typeof window.renderAssistantMarkdown === "function"
        ? window.renderAssistantMarkdown
        : (value) => `<p>${escapeHtml(value).replace(/\n/g, "<br />")}</p>`;
    return {
      bubbleClass: "bubble markdown-body",
      html: !text && streaming
        ? `<p class="stream-placeholder">正在生成...</p>`
        : renderMarkdown(text || ""),
    };
  }

  return {
    bubbleClass: "bubble",
    html: escapeHtml(text || "").replace(/\n/g, "<br />"),
  };
}

function renderProjects() {
  if (!state.projects.length) {
    projectListEl.innerHTML = `<div class="empty-state">还没有项目</div>`;
    return;
  }

  projectListEl.innerHTML = state.projects
    .map((project) => {
      const isActive = project === state.activeProject;
      const documents = state.projectDocuments[project];
      const hasDocuments = Array.isArray(documents) && documents.length > 0;
      const documentCount = Array.isArray(documents) ? documents.length : 0;
      const isDeletingProject = Boolean(state.deletingProjects[project]);

      return `
        <div class="project-tree ${isActive ? "expanded" : ""}">
          <div class="project-row">
            <button class="project-item ${isActive ? "active" : ""}" data-project="${escapeHtml(project)}" type="button">
              <span class="project-item-name">${escapeHtml(project)}</span>
              <span class="project-item-meta">
                <span class="project-item-count">${documentCount}</span>
                <span class="project-item-arrow">${isActive ? "▾" : "▸"}</span>
              </span>
            </button>
            <button
              class="project-delete-btn"
              type="button"
              data-project="${escapeHtml(project)}"
              title="删除项目"
              aria-label="删除项目"
              ${isDeletingProject ? "disabled" : ""}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 7h2v8h-2v-8zm4 0h2v8h-2v-8zM7 10h2v8H7v-8zm-1 10h12l1-11H5l1 11z"></path>
              </svg>
            </button>
          </div>
          ${
            isActive
              ? `<div class="document-list">
                  ${
                    documents === undefined
                      ? `<div class="document-empty">正在加载文档...</div>`
                      : hasDocuments
                        ? documents
                            .map(
                              (document) => {
                                const deletingKey = `${project}::${document}`;
                                const isDeleting = Boolean(state.deletingDocuments[deletingKey]);
                                return `
                                  <div class="document-row">
                                    <div class="document-item" title="${escapeHtml(document)}">${escapeHtml(document)}</div>
                                    <button
                                      class="document-delete-btn"
                                      type="button"
                                      data-project="${escapeHtml(project)}"
                                      data-document="${escapeHtml(document)}"
                                      title="删除文档"
                                      aria-label="删除文档"
                                      ${isDeleting ? "disabled" : ""}
                                    >
                                      <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <path d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 7h2v8h-2v-8zm4 0h2v8h-2v-8zM7 10h2v8H7v-8zm-1 10h12l1-11H5l1 11z"></path>
                                      </svg>
                                    </button>
                                  </div>
                                `;
                              }
                            )
                            .join("")
                        : `<div class="document-empty">该项目还没有上传文档</div>`
                  }
                </div>`
              : ""
          }
        </div>
      `;
    })
    .join("");

  document.querySelectorAll(".project-item").forEach((button) => {
    button.addEventListener("click", async () => {
      await setActiveProject(button.dataset.project);
    });
  });

  document.querySelectorAll(".document-delete-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteDocument(button.dataset.project, button.dataset.document);
    });
  });

  document.querySelectorAll(".project-delete-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteProject(button.dataset.project);
    });
  });
}

function renderConversations() {
  newConversationBtnEl.disabled = !state.activeProject;

  if (!state.activeProject) {
    conversationListEl.innerHTML = `<div class="conversation-empty">请选择项目后查看历史对话</div>`;
    return;
  }

  const conversations = state.projectConversations[state.activeProject];
  if (conversations === undefined) {
    conversationListEl.innerHTML = `<div class="conversation-empty">正在加载对话...</div>`;
    return;
  }

  if (!conversations.length) {
    conversationListEl.innerHTML = `<div class="conversation-empty">当前项目还没有历史对话</div>`;
    return;
  }

  conversationListEl.innerHTML = conversations
    .map((conversation) => {
      const isActive = conversation.conversation_id === state.activeConversationId;
      const deletingKey = conversationKey(state.activeProject, conversation.conversation_id);
      const isDeleting = Boolean(state.deletingConversations[deletingKey]);
      const meta = `${conversation.message_count || 0} 条消息`;

      return `
        <div class="conversation-chip ${isActive ? "active" : ""}">
          <button
            class="conversation-item ${isActive ? "active" : ""}"
            type="button"
            data-conversation-id="${escapeHtml(conversation.conversation_id)}"
            title="${escapeHtml(conversation.title || "新对话")}" 
          >
            <span class="conversation-item-title">${escapeHtml(conversation.title || "新对话")}</span>
            <span class="conversation-item-meta">${escapeHtml(meta)}</span>
          </button>
          <button
            class="conversation-delete-btn"
            type="button"
            data-conversation-id="${escapeHtml(conversation.conversation_id)}"
            title="删除对话"
            aria-label="删除对话"
            ${isDeleting ? "disabled" : ""}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M9 3h6l1 2h4v2H4V5h4l1-2zm1 7h2v8h-2v-8zm4 0h2v8h-2v-8zM7 10h2v8H7v-8zm-1 10h12l1-11H5l1 11z"></path>
            </svg>
          </button>
        </div>
      `;
    })
    .join("");

  document.querySelectorAll(".conversation-item").forEach((button) => {
    button.addEventListener("click", async () => {
      await setActiveConversation(button.dataset.conversationId);
    });
  });

  document.querySelectorAll(".conversation-delete-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteConversation(button.dataset.conversationId);
    });
  });
}

async function loadProjectDocuments(projectName, force = false) {
  if (!projectName) {
    return;
  }

  if (!force && Array.isArray(state.projectDocuments[projectName])) {
    return;
  }

  state.projectDocuments[projectName] = undefined;
  renderProjects();

  const data = await requestJson(`/api/projects/${encodeURIComponent(projectName)}/documents`);
  state.projectDocuments[projectName] = data.documents || [];
  renderProjects();
}

async function loadConversationDetail(projectName, conversationId, force = false) {
  if (!projectName || !conversationId) {
    renderConversationMessages([]);
    return null;
  }

  const key = conversationKey(projectName, conversationId);
  if (!force && state.conversationDetails[key]) {
    if (state.activeProject === projectName && state.activeConversationId === conversationId) {
      renderConversationMessages(state.conversationDetails[key].messages || []);
    }
    return state.conversationDetails[key];
  }

  const data = await requestJson(
    `/api/projects/${encodeURIComponent(projectName)}/conversations/${encodeURIComponent(conversationId)}`
  );
  state.conversationDetails[key] = data;

  if (state.activeProject === projectName && state.activeConversationId === conversationId) {
    renderConversationMessages(data.messages || []);
  }
  return data;
}

async function loadConversations(projectName, force = false) {
  if (!projectName) {
    return;
  }

  if (!force && Array.isArray(state.projectConversations[projectName])) {
    renderConversations();
    return;
  }

  state.projectConversations[projectName] = undefined;
  renderConversations();

  const data = await requestJson(`/api/projects/${encodeURIComponent(projectName)}/conversations`);
  const conversations = data.conversations || [];
  state.projectConversations[projectName] = conversations;
  renderConversations();

  if (state.activeProject !== projectName) {
    return;
  }

  const hasActiveConversation = conversations.some(
    (conversation) => conversation.conversation_id === state.activeConversationId
  );

  if (hasActiveConversation && state.activeConversationId) {
    await loadConversationDetail(projectName, state.activeConversationId, force);
    return;
  }

  if (conversations.length) {
    await setActiveConversation(conversations[0].conversation_id);
    return;
  }

  state.activeConversationId = null;
  renderConversations();
  renderConversationMessages([]);
}

async function setActiveProject(projectName) {
  state.activeProject = projectName;
  state.activeConversationId = null;
  activeProjectNameEl.textContent = projectName || "未选择项目";
  projectStatusEl.textContent = projectName ? `当前项目: ${projectName}` : "请选择左侧项目";
  renderProjects();
  renderConversations();
  renderConversationMessages([]);
  renderChatComposer();

  if (!projectName) {
    return;
  }

  try {
    await loadProjectDocuments(projectName);
  } catch (error) {
    state.projectDocuments[projectName] = [];
    renderProjects();
    appendMessage("assistant", `加载项目文档失败：${error.message}`);
  }

  try {
    await loadConversations(projectName, true);
  } catch (error) {
    state.projectConversations[projectName] = [];
    renderConversations();
    appendMessage("assistant", `加载历史对话失败：${error.message}`);
  }
}

async function setActiveConversation(conversationId) {
  state.activeConversationId = conversationId || null;
  renderConversations();

  if (!state.activeProject || !state.activeConversationId) {
    renderConversationMessages([]);
    return;
  }

  try {
    await loadConversationDetail(state.activeProject, state.activeConversationId, true);
  } catch (error) {
    appendMessage("assistant", `加载对话失败：${error.message}`);
  }
}

function updateMessageElement(messageEl, role, text, sources = [], options = {}) {
  const rendered = renderMessageBubble(role, text, options);
  messageEl.classList.toggle("streaming", Boolean(options.streaming));
  messageEl.innerHTML = `<div class="${rendered.bubbleClass}">${rendered.html}</div>${renderSourcesHtml(sources)}`;
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

function appendMessage(role, text, sources = [], options = {}) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;
  chatMessagesEl.appendChild(wrapper);
  updateMessageElement(wrapper, role, text, sources, options);
  return wrapper;
}

async function readErrorResponse(response) {
  const data = await response.json().catch(() => null);
  if (data?.detail) {
    return data.detail;
  }

  const text = await response.text().catch(() => "");
  return text || "请求失败";
}

async function loadProjects() {
  const data = await requestJson("/api/projects");
  state.projects = data.projects || [];

  if (state.activeProject && !state.projects.includes(state.activeProject)) {
    state.activeProject = null;
    state.activeConversationId = null;
  }

  if (!state.activeProject && state.projects.length) {
    await setActiveProject(state.projects[0]);
    return;
  }

  renderProjects();
  renderConversations();
}

function clearProjectSelection() {
  state.activeProject = null;
  state.activeConversationId = null;
  activeProjectNameEl.textContent = "未选择项目";
  projectStatusEl.textContent = "请选择左侧项目";
  renderProjects();
  renderConversations();
  renderConversationMessages([]);
  renderChatComposer();
}

async function createProject() {
  const name = projectNameInputEl.value.trim();
  if (!name) {
    alert("请输入项目名");
    return;
  }

  const data = await requestJson("/api/projects", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });

  state.projects = data.projects || [];
  state.projectDocuments[data.project_name] = [];
  state.projectConversations[data.project_name] = [];
  projectNameInputEl.value = "";
  await setActiveProject(data.project_name);
}

async function createConversation() {
  if (!state.activeProject) {
    alert("请先选择项目");
    return null;
  }

  const data = await requestJson(
    `/api/projects/${encodeURIComponent(state.activeProject)}/conversations`,
    {
      method: "POST",
    }
  );

  const key = conversationKey(state.activeProject, data.conversation_id);
  state.conversationDetails[key] = {
    ...data,
    messages: [],
  };
  await loadConversations(state.activeProject, true);
  await setActiveConversation(data.conversation_id);
  return data;
}

async function uploadPdf() {
  if (!state.activeProject) {
    alert("请先选择项目");
    return;
  }

  const file = pdfInputEl.files[0];
  if (!file) {
    alert("请先选择 PDF 文件");
    return;
  }

  uploadStatusEl.textContent = "正在上传并构建索引，请稍候...";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await requestJson(
      `/api/projects/${encodeURIComponent(state.activeProject)}/upload`,
      {
        method: "POST",
        body: formData,
      }
    );
    uploadStatusEl.textContent = `完成: ${data.filename}，已写入 ${data.indexing.inserted_records} 条向量`;
    pdfInputEl.value = "";
    await loadProjectDocuments(state.activeProject, true);
  } catch (error) {
    uploadStatusEl.textContent = error.message;
  }
}

async function deleteDocument(projectName, documentName) {
  if (!projectName || !documentName) {
    return;
  }

  const confirmed = window.confirm(`确定删除文档《${documentName}》吗？这会同时删除索引内容。`);
  if (!confirmed) {
    return;
  }

  const deletingKey = `${projectName}::${documentName}`;
  state.deletingDocuments[deletingKey] = true;
  renderProjects();

  try {
    await requestJson(
      `/api/projects/${encodeURIComponent(projectName)}/documents/${encodeURIComponent(documentName)}`,
      {
        method: "DELETE",
      }
    );
    uploadStatusEl.textContent = `已删除: ${documentName}`;
    await loadProjectDocuments(projectName, true);
  } catch (error) {
    appendMessage("assistant", `删除文档失败：${error.message}`);
  } finally {
    delete state.deletingDocuments[deletingKey];
    renderProjects();
  }
}

async function deleteConversation(conversationId) {
  if (!state.activeProject || !conversationId) {
    return;
  }

  const confirmed = window.confirm("确定删除这段历史对话吗？删除后无法恢复。");
  if (!confirmed) {
    return;
  }

  const deletingKey = conversationKey(state.activeProject, conversationId);
  state.deletingConversations[deletingKey] = true;
  renderConversations();

  try {
    await requestJson(
      `/api/projects/${encodeURIComponent(state.activeProject)}/conversations/${encodeURIComponent(conversationId)}`,
      {
        method: "DELETE",
      }
    );

    delete state.conversationDetails[deletingKey];
    await loadConversations(state.activeProject, true);

    if (state.activeConversationId === conversationId) {
      const conversations = state.projectConversations[state.activeProject] || [];
      if (!conversations.length) {
        state.activeConversationId = null;
        renderConversationMessages([]);
      }
    }
  } catch (error) {
    appendMessage("assistant", `删除对话失败：${error.message}`);
  } finally {
    delete state.deletingConversations[deletingKey];
    renderConversations();
  }
}

async function deleteProject(projectName) {
  if (!projectName) {
    return;
  }

  const confirmed = window.confirm(
    `确定删除项目《${projectName}》吗？这会同时删除该项目下的 PDF、向量库、解析产物和历史对话。`
  );
  if (!confirmed) {
    return;
  }

  state.deletingProjects[projectName] = true;
  renderProjects();

  try {
    const data = await requestJson(`/api/projects/${encodeURIComponent(projectName)}`, {
      method: "DELETE",
    });

    delete state.projectDocuments[projectName];
    delete state.projectConversations[projectName];
    Object.keys(state.conversationDetails).forEach((key) => {
      if (key.startsWith(`${projectName}::`)) {
        delete state.conversationDetails[key];
      }
    });
    state.projects = data.projects || [];

    if (state.activeProject === projectName) {
      if (state.projects.length) {
        await setActiveProject(state.projects[0]);
      } else {
        clearProjectSelection();
      }
    } else {
      renderProjects();
    }

    uploadStatusEl.textContent = `已删除项目: ${projectName}`;
  } catch (error) {
    appendMessage("assistant", `删除项目失败：${error.message}`);
  } finally {
    delete state.deletingProjects[projectName];
    renderProjects();
  }
}

async function sendMessage() {
  if (state.isSendingMessage) {
    return;
  }

  if (!state.activeProject) {
    renderChatComposer();
    alert("请先选择项目");
    return;
  }

  const query = chatInputEl.value.trim();
  if (!query) {
    renderChatComposer();
    return;
  }

  let conversationId = state.activeConversationId;
  if (!conversationId) {
    const createdConversation = await createConversation();
    conversationId = createdConversation?.conversation_id || null;
  }

  if (!conversationId) {
    appendMessage("assistant", "创建对话失败，请稍后重试。");
    return;
  }

  appendMessage("user", query);
  chatInputEl.value = "";
  const assistantMessageEl = appendMessage("assistant", "", [], { markdown: false, streaming: true });
  let assistantText = "";
  let finalPayload = null;
  state.isSendingMessage = true;
  renderChatComposer();

  try {
    const response = await fetch(
      `/api/projects/${encodeURIComponent(state.activeProject)}/chat`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query, conversation_id: conversationId }),
      }
    );

    if (!response.ok) {
      throw new Error(await readErrorResponse(response));
    }

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.startsWith("text/event-stream")) {
      throw new Error("后端未返回 SSE 流");
    }

    await consumeSseStream(response, {
      start(payload) {
        state.activeConversationId = payload.conversation_id || conversationId;
      },
      token(payload) {
        assistantText += payload.delta || "";
        updateMessageElement(assistantMessageEl, "assistant", assistantText, [], { markdown: false, streaming: true });
      },
      done(payload) {
        finalPayload = payload;
        assistantText = payload.answer || assistantText;
        updateMessageElement(assistantMessageEl, "assistant", assistantText, payload.sources || [], { markdown: true });
      },
      error(payload) {
        throw new Error(payload.detail || "流式请求失败");
      },
    });

    state.activeConversationId = finalPayload?.conversation_id || state.activeConversationId || conversationId;
    renderConversations();
    await loadConversationDetail(state.activeProject, state.activeConversationId, true);
    await loadConversations(state.activeProject, true);
  } catch (error) {
    if (assistantText) {
      appendMessage("assistant", `流式请求中断：${error.message}`);
    } else {
      updateMessageElement(assistantMessageEl, "assistant", `请求失败：${error.message}`);
    }
  } finally {
    state.isSendingMessage = false;
    renderChatComposer();
  }
}

function toggleUploadPanel() {
  state.uploadPanelHidden = !state.uploadPanelHidden;
  renderUploadPanelVisibility();
}

createProjectBtnEl.addEventListener("click", () => {
  createProject().catch((error) => {
    appendMessage("assistant", `创建项目失败：${error.message}`);
  });
});

newConversationBtnEl.addEventListener("click", () => {
  createConversation().catch((error) => {
    appendMessage("assistant", `创建对话失败：${error.message}`);
  });
});

uploadPdfBtnEl.addEventListener("click", uploadPdf);
sendChatBtnEl.addEventListener("click", () => {
  sendMessage().catch((error) => {
    appendMessage("assistant", `发送消息失败：${error.message}`);
  });
});
toggleUploadPanelBtnEl.addEventListener("click", toggleUploadPanel);
hideUploadPanelBtnEl.addEventListener("click", toggleUploadPanel);

chatInputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage().catch((error) => {
      appendMessage("assistant", `发送消息失败：${error.message}`);
    });
  }
});
chatInputEl.addEventListener("input", renderChatComposer);

renderUploadPanelVisibility();
renderConversations();
renderChatComposer();

loadProjects().catch((error) => {
  appendMessage("assistant", `初始化失败：${error.message}`);
});
