(function () {
  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function protectInlineHtml(value, replacer) {
    const tokens = [];
    const pushToken = (html) => {
      const token = `@@MD_TOKEN_${tokens.length}@@`;
      tokens.push({ token, html });
      return token;
    };

    let output = replacer(value, pushToken);
    output = escapeHtml(output);
    for (const { token, html } of tokens) {
      output = output.replaceAll(token, html);
    }
    return output;
  }

  function renderInlineMarkdown(text) {
    let value = String(text ?? "");

    value = protectInlineHtml(value, (raw, pushToken) => {
      let next = raw;
      next = next.replace(/`([^`]+)`/g, (_, code) => pushToken(`<code>${escapeHtml(code)}</code>`));
      next = next.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) =>
        pushToken(`<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(label)}</a>`)
      );
      next = next.replace(/(^|[\s(])(https?:\/\/[^\s<]+)(?![^<]*>)/g, (_, prefix, url) =>
        `${prefix}${pushToken(`<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(url)}</a>`)}`
      );
      return next;
    });

    value = value.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    value = value.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    value = value.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
    return value;
  }

  function parseTableRow(line) {
    let normalized = line.trim();
    if (normalized.startsWith("|")) {
      normalized = normalized.slice(1);
    }
    if (normalized.endsWith("|")) {
      normalized = normalized.slice(0, -1);
    }
    return normalized.split("|").map((cell) => cell.trim());
  }

  function renderTable(lines) {
    const rows = lines.map(parseTableRow);
    if (rows.length < 2) {
      return null;
    }

    const separatorCells = rows[1];
    if (!separatorCells.every((cell) => /^:?-{3,}:?$/.test(cell))) {
      return null;
    }

    const header = rows[0].map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("");
    const body = rows
      .slice(2)
      .map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`)
      .join("");

    return `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderList(lines, ordered) {
    const tag = ordered ? "ol" : "ul";
    const items = lines
      .map((line) => {
        const raw = ordered
          ? line.replace(/^\d+\.\s+/, "")
          : line.replace(/^\s*[-*+]\s+/, "");
        const taskMatch = raw.match(/^\[( |x|X)\]\s+(.*)$/);
        if (!taskMatch) {
          return `<li>${renderInlineMarkdown(raw)}</li>`;
        }

        const checked = taskMatch[1].toLowerCase() === "x";
        return `<li class="task-list-item"><input type="checkbox" disabled ${checked ? "checked" : ""} /> <span>${renderInlineMarkdown(taskMatch[2])}</span></li>`;
      })
      .join("");
    return `<${tag}>${items}</${tag}>`;
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown ?? "").replace(/\r\n/g, "\n").split("\n");
    const html = [];
    let index = 0;

    while (index < lines.length) {
      const line = lines[index];

      if (!line.trim()) {
        index += 1;
        continue;
      }

      const fenceMatch = line.match(/^```([a-zA-Z0-9_-]+)?\s*$/);
      if (fenceMatch) {
        const language = fenceMatch[1] ? ` class="language-${escapeHtml(fenceMatch[1])}"` : "";
        index += 1;
        const codeLines = [];
        while (index < lines.length && !/^```/.test(lines[index])) {
          codeLines.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) {
          index += 1;
        }
        html.push(`<pre><code${language}>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        continue;
      }

      if (line.includes("|")) {
        const tableLines = [];
        let tableIndex = index;
        while (tableIndex < lines.length && lines[tableIndex].includes("|")) {
          tableLines.push(lines[tableIndex]);
          tableIndex += 1;
        }
        const tableHtml = renderTable(tableLines);
        if (tableHtml) {
          html.push(tableHtml);
          index = tableIndex;
          continue;
        }
      }

      const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
      if (headingMatch) {
        const level = headingMatch[1].length;
        html.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
        index += 1;
        continue;
      }

      if (/^>\s?/.test(line)) {
        const quoteLines = [];
        while (index < lines.length && /^>\s?/.test(lines[index])) {
          quoteLines.push(lines[index].replace(/^>\s?/, ""));
          index += 1;
        }
        html.push(`<blockquote><p>${quoteLines.map(renderInlineMarkdown).join("<br />")}</p></blockquote>`);
        continue;
      }

      if (/^\d+\.\s+/.test(line)) {
        const listLines = [];
        while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
          listLines.push(lines[index]);
          index += 1;
        }
        html.push(renderList(listLines, true));
        continue;
      }

      if (/^\s*[-*+]\s+/.test(line)) {
        const listLines = [];
        while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) {
          listLines.push(lines[index]);
          index += 1;
        }
        html.push(renderList(listLines, false));
        continue;
      }

      const paragraphLines = [];
      while (
        index < lines.length &&
        lines[index].trim() &&
        !/^(#{1,6})\s+/.test(lines[index]) &&
        !/^```/.test(lines[index]) &&
        !/^>\s?/.test(lines[index]) &&
        !/^\d+\.\s+/.test(lines[index]) &&
        !/^\s*[-*+]\s+/.test(lines[index])
      ) {
        paragraphLines.push(lines[index]);
        index += 1;
      }
      html.push(`<p>${paragraphLines.map(renderInlineMarkdown).join("<br />")}</p>`);
    }

    return html.join("");
  }

  window.renderAssistantMarkdown = renderMarkdown;
})();
