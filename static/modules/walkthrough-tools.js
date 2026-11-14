/* ==========================================================================
 * ACG Vault v3.3.0 — Modular Walkthrough & Mermaid Flowchart Compiler
 * Extracted from monolithic app.js for clean separation of concerns.
 * Exposes window.AcgWalkthroughTools
 * ========================================================================== */
(function () {
  'use strict';
  if (window.AcgWalkthroughTools) return;

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function compileMermaidToVisualHtml(code) {
    const lines = (code || '').split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
    let subgraphTitle = '剧情分支与路线流程图';
    const nodeLabels = {};
    const edges = [];

    const parseNodeToken = function (tok) {
      if (!tok) return '';
      const m = tok.match(/^([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^)]+)\)|\{([^}]+)\})?$/);
      if (m) {
        const id = m[1];
        const label = (m[2] || m[3] || m[4] || '').trim().replace(/^"|"$/g, '');
        if (label) nodeLabels[id] = label;
        return nodeLabels[id] || id;
      }
      return tok.replace(/[\[\]{}()"]/g, '').trim();
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (/^(flowchart|graph)\b/i.test(line) || line === 'end') continue;
      const subMatch = line.match(/^subgraph\s+(.+)$/i);
      if (subMatch) {
        subgraphTitle = subMatch[1].trim();
        continue;
      }
      const edgeMatch =
        line.match(/^(.+?)\s*--(?:\|\s*([^|]+?)\s*\|)?-->\s*(.+)$/) ||
        line.match(/^(.+?)\s*(?:-->|---|==>)\s*(?:\|\s*([^|]+?)\s*\|\s*)?(.+)$/);
      if (edgeMatch) {
        const leftRaw = edgeMatch[1].trim();
        const cond = (edgeMatch[2] || '').trim();
        const rightRaw = edgeMatch[3].trim();

        const leftParts = leftRaw.split(/\s*&\s*/).map(parseNodeToken);
        const rightParts = rightRaw.split(/\s*&\s*/).map(parseNodeToken);

        edges.push({
          from: leftParts.join(' + '),
          cond: cond,
          to: rightParts.join(' / ')
        });
      }
    }

    if (edges.length === 0) {
      return '<pre class="text-xs font-mono text-slate-300 bg-slate-950 p-3 rounded-xl overflow-x-auto">' + escapeHtml(code) + '</pre>';
    }

    const edgeHtml = edges.map(function (e) {
      const condBadge = e.cond
        ? '<span class="mermaid-edge-label">' + escapeHtml(e.cond) + '</span><span class="mermaid-arrow">→</span>'
        : '<span class="mermaid-arrow">⟶</span>';
      return (
        '<div class="mermaid-edge-row">' +
          '<span class="mermaid-node-pill">' + escapeHtml(e.from) + '</span>' +
          condBadge +
          '<span class="mermaid-node-pill">' + escapeHtml(e.to) + '</span>' +
        '</div>'
      );
    }).join('');

    return (
      '<div class="mermaid-flow-container">' +
        '<div class="mermaid-flow-title">' +
          '<span>🗺️ ' + escapeHtml(subgraphTitle) + '</span>' +
        '</div>' +
        '<div class="mermaid-flow-steps">' + edgeHtml + '</div>' +
      '</div>'
    );
  }

  window.AcgWalkthroughTools = {
    escapeHtml: escapeHtml,
    compileMermaidToVisualHtml: compileMermaidToVisualHtml
  };
})();
