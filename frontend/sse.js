(function (root, factory) {
  const api = factory();

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }

  root.chatSse = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  function parseSseEventBlock(block) {
    const lines = block.split(/\r?\n/);
    let eventName = "message";
    const dataLines = [];

    lines.forEach((line) => {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim() || "message";
        return;
      }
      if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    });

    if (!dataLines.length) {
      return null;
    }

    return {
      event: eventName,
      data: JSON.parse(dataLines.join("\n")),
    };
  }

  async function consumeSseStream(response, handlers) {
    if (!response.body) {
      throw new Error("浏览器不支持流式响应");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let reachedTerminalEvent = false;

    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        const parsed = parseSseEventBlock(block);
        if (!parsed) {
          continue;
        }

        const handler = handlers[parsed.event];
        if (handler) {
          handler(parsed.data);
        }

        if (parsed.event === "done" || parsed.event === "error") {
          reachedTerminalEvent = true;
          break;
        }
      }

      if (reachedTerminalEvent) {
        await reader.cancel().catch(() => {});
        return;
      }

      if (done) {
        if (buffer.trim()) {
          const parsed = parseSseEventBlock(buffer);
          if (parsed && handlers[parsed.event]) {
            handlers[parsed.event](parsed.data);
          }
        }
        return;
      }
    }
  }

  return {
    parseSseEventBlock,
    consumeSseStream,
  };
});
