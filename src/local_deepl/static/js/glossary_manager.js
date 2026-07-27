/*
 * Glossary Multi-Source Import & Library Management
 * -----------------------------------------------
 * Wires up the new Glossary Library panel and the import modal, and finally
 * connects the long-unwired `#glossary-save-btn` to the server (POST to
 * /api/glossary/import with format=json_pairs). The file is fully DOM-
 * CreateElement-driven; all updates use replaceChildren + appendChild to
 * satisfy the static-JS XSS-safety guard.
 */
(function () {
    "use strict";

    if (window.__glossaryManagerLoaded) {
        return;
    }
    window.__glossaryManagerLoaded = true;

    const LIBRARY_ENDPOINT = "/api/glossary/library";
    const IMPORT_ENDPOINT = "/api/glossary/import";
    const PREVIEW_ENDPOINT = "/api/glossary/library/preview";
    const TOGGLE_ENDPOINT = (id) => `/api/glossary/library/${encodeURIComponent(id)}/enable`;
    const DELETE_ENDPOINT = (id) => `/api/glossary/library/${encodeURIComponent(id)}`;
    const ENTRIES_ENDPOINT = (id) => `/api/glossary/library/${encodeURIComponent(id)}/entries`;

    function getRefs() {
        return (typeof window.state_and_api_refs !== "undefined"
            && window.state_and_api_refs
            && typeof window.state_and_api_refs === "object")
            ? window.state_and_api_refs
            : (window.refs || null);
    }

    function showToast(message, level) {
        if (typeof window.showToast === "function") {
            window.showToast(message, level || "info");
            return;
        }
        const container = document.getElementById("toast-container");
        if (!container) return;
        const toast = document.createElement("div");
        toast.className = "toast " + (level || "info");
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 4000);
    }

    function readTextareaPairs(text) {
        const lines = (text || "").split(/\r?\n/);
        const entries = [];
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith("#")) continue;
            const eq = trimmed.indexOf("=");
            if (eq <= 0) continue;
            const source = trimmed.slice(0, eq).trim();
            const target = trimmed.slice(eq + 1).trim();
            if (!source || !target) continue;
            entries.push({ source, target });
        }
        return entries;
    }

    async function fetchJson(url, options) {
        const opts = Object.assign({ method: "GET", headers: {} }, options || {});
        if (window.localStorage && window.localStorage.getItem("session_token")) {
            opts.headers["X-Session-Token"] = window.localStorage.getItem("session_token");
        }
        const res = await fetch(url, opts);
        if (!res.ok) {
            let detail = res.statusText;
            try {
                const body = await res.json();
                detail = (body && body.detail) || JSON.stringify(body);
            } catch (err) {
                // ignore parse failures
            }
            throw new Error(`${res.status} ${detail}`);
        }
        return res.json();
    }

    function buildRow(item) {
        const tr = document.createElement("tr");
        tr.dataset.glossaryId = item.id;

        const cells = [
            { text: item.name || "" },
            { text: item.format || "" },
            { text: String(item.entry_count || 0) },
            { text: item.group || "default" },
            { text: String(item.priority == null ? 0 : item.priority) },
        ];
        for (const c of cells) {
            const td = document.createElement("td");
            td.textContent = c.text;
            tr.appendChild(td);
        }

        const enabledTd = document.createElement("td");
        const enabledLabel = document.createElement("label");
        enabledLabel.className = "toggle-row glossary-toggle-row";
        const enabledInput = document.createElement("input");
        enabledInput.type = "checkbox";
        enabledInput.checked = item.enabled !== false;
        enabledInput.addEventListener("change", () => {
            void toggleItem(item.id, enabledInput.checked);
        });
        const enabledSpan = document.createElement("span");
        enabledSpan.textContent = item.enabled !== false ? "Enabled" : "Disabled";
        enabledLabel.appendChild(enabledInput);
        enabledLabel.appendChild(enabledSpan);
        enabledTd.appendChild(enabledLabel);
        tr.appendChild(enabledTd);

        const actionsTd = document.createElement("td");
        const actionsWrap = document.createElement("div");
        actionsWrap.className = "glossary-row-actions";

        const viewBtn = document.createElement("button");
        viewBtn.className = "btn-chip";
        viewBtn.textContent = "View";
        viewBtn.addEventListener("click", () => void viewEntries(item.id));
        actionsWrap.appendChild(viewBtn);

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "btn-chip danger";
        deleteBtn.textContent = "Delete";
        deleteBtn.addEventListener("click", () => void deleteItem(item.id));
        actionsWrap.appendChild(deleteBtn);

        actionsTd.appendChild(actionsWrap);
        tr.appendChild(actionsTd);

        return tr;
    }

    function renderEmpty(tbody) {
        const tr = document.createElement("tr");
        tr.className = "glossary-empty";
        const td = document.createElement("td");
        td.colSpan = 7;
        td.textContent = "No glossaries yet. Use Import to add one.";
        tr.appendChild(td);
        tbody.appendChild(tr);
    }

    async function loadLibrary() {
        const refs = getRefs();
        const tbody = refs && refs.glossaryLibraryTbody;
        if (!tbody) return;
        tbody.replaceChildren();
        let items = [];
        try {
            items = await fetchJson(LIBRARY_ENDPOINT);
        } catch (err) {
            showToast(`Failed to load glossary library: ${err.message}`, "error");
            renderEmpty(tbody);
            return;
        }
        if (!Array.isArray(items) || items.length === 0) {
            renderEmpty(tbody);
            return;
        }
        const fragment = document.createDocumentFragment();
        items.forEach((item) => fragment.appendChild(buildRow(item)));
        tbody.appendChild(fragment);
    }

    async function toggleItem(id, enabled) {
        try {
            await fetchJson(TOGGLE_ENDPOINT(id), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enabled }),
            });
            showToast(`Glossary ${enabled ? "enabled" : "disabled"}.`, "info");
        } catch (err) {
            showToast(`Failed to update glossary: ${err.message}`, "error");
        }
    }

    async function deleteItem(id) {
        try {
            await fetchJson(DELETE_ENDPOINT(id), { method: "DELETE" });
            showToast("Glossary deleted.", "info");
            await loadLibrary();
        } catch (err) {
            showToast(`Failed to delete glossary: ${err.message}`, "error");
        }
    }

    async function viewEntries(id) {
        try {
            const data = await fetchJson(ENTRIES_ENDPOINT(id));
            const refs = getRefs();
            const panel = refs && refs.glossaryPreviewPanel;
            if (!panel) return;
            panel.replaceChildren();
            const heading = document.createElement("h5");
            heading.textContent = `${data.name || id} — ${(data.entries || []).length} entries`;
            panel.appendChild(heading);
            const list = document.createElement("div");
            list.className = "glossary-preview-list";
            const fragment = document.createDocumentFragment();
            for (const entry of data.entries || []) {
                const row = document.createElement("div");
                row.className = "glossary-preview-row";
                const left = document.createElement("span");
                left.textContent = entry.source || "";
                const arrow = document.createElement("span");
                arrow.textContent = " → ";
                const right = document.createElement("span");
                right.textContent = entry.target || "";
                row.appendChild(left);
                row.appendChild(arrow);
                row.appendChild(right);
                fragment.appendChild(row);
            }
            list.appendChild(fragment);
            panel.appendChild(list);
            panel.classList.remove("hidden");
        } catch (err) {
            showToast(`Failed to load entries: ${err.message}`, "error");
        }
    }

    async function loadPreview() {
        const refs = getRefs();
        const panel = refs && refs.glossaryPreviewPanel;
        if (!panel) return;
        panel.replaceChildren();
        panel.classList.remove("hidden");
        const loading = document.createElement("div");
        loading.textContent = "Loading preview…";
        panel.appendChild(loading);
        try {
            const data = await fetchJson(PREVIEW_ENDPOINT);
            panel.replaceChildren();
            const heading = document.createElement("h5");
            heading.textContent = `Preview — ${data.count || 0} merged entries`;
            panel.appendChild(heading);
            const enabledList = document.createElement("div");
            enabledList.className = "glossary-preview-meta";
            const enabledLabel = document.createElement("span");
            enabledLabel.textContent = "Enabled: ";
            const enabledValue = document.createElement("strong");
            enabledValue.textContent = (data.enabled_glossaries || []).join(", ") || "(none)";
            enabledList.appendChild(enabledLabel);
            enabledList.appendChild(enabledValue);
            panel.appendChild(enabledList);

            const conflicts = Array.isArray(data.conflicts) ? data.conflicts : [];
            if (conflicts.length === 0) {
                const ok = document.createElement("p");
                ok.textContent = "No conflicts across enabled glossaries.";
                panel.appendChild(ok);
            } else {
                const list = document.createElement("ul");
                list.className = "glossary-conflict-list";
                const fragment = document.createDocumentFragment();
                for (const conflict of conflicts) {
                    const li = document.createElement("li");
                    li.textContent = `${conflict.source}: ${(conflict.targets || []).join(" | ")}`;
                    fragment.appendChild(li);
                }
                list.appendChild(fragment);
                panel.appendChild(list);
            }
        } catch (err) {
            panel.replaceChildren();
            const msg = document.createElement("p");
            msg.textContent = `Failed to load preview: ${err.message}`;
            panel.appendChild(msg);
        }
    }

    function setImportStatus(message, level) {
        const refs = getRefs();
        const el = refs && refs.glossaryImportStatus;
        if (!el) return;
        el.textContent = message || "";
        el.classList.remove("error", "success", "info");
        el.classList.add(level || "info");
    }

    function showImportFormatGroups(format) {
        const refs = getRefs();
        if (!refs) return;
        const showText = format === "json_pairs" || format === "csv" || format === "tsv";
        const showFile = format === "csv" || format === "tsv"
            || format === "xliff" || format === "tbx" || format === "tmx";
        const showGit = format === "git_glossary";
        const showSql = format === "sql_table";

        toggleClass(refs.glossaryImportTextGroup, "hidden", !showText);
        toggleClass(refs.glossaryImportFileGroup, "hidden", !showFile);
        toggleClass(refs.glossaryImportGitGroup, "hidden", !showGit);
        toggleClass(refs.glossaryImportSqlGroup, "hidden", !showSql);
    }

    function toggleClass(el, cls, on) {
        if (!el) return;
        el.classList.toggle(cls, !!on);
    }

    function openImportModal() {
        const refs = getRefs();
        if (!refs || !refs.glossaryImportModal) return;
        const format = refs.glossaryImportFormat
            ? refs.glossaryImportFormat.value
            : "json_pairs";
        showImportFormatGroups(format);
        setImportStatus("");
        refs.glossaryImportModal.classList.remove("hidden");
    }

    function closeImportModal() {
        const refs = getRefs();
        if (!refs || !refs.glossaryImportModal) return;
        refs.glossaryImportModal.classList.add("hidden");
    }

    function fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = () => reject(reader.error || new Error("FileReader failed"));
            reader.onload = () => {
                const result = reader.result;
                if (typeof result === "string") {
                    resolve(result.split(",").pop() || "");
                    return;
                }
                const bytes = new Uint8Array(result);
                let binary = "";
                for (let i = 0; i < bytes.byteLength; i += 1) {
                    binary += String.fromCharCode(bytes[i]);
                }
                resolve(btoa(binary));
            };
            reader.readAsDataURL(file);
        });
    }

    async function submitImport() {
        const refs = getRefs();
        if (!refs) return;
        const format = refs.glossaryImportFormat ? refs.glossaryImportFormat.value : "json_pairs";
        const name = refs.glossaryImportName ? refs.glossaryImportName.value.trim() : "";
        const source = { format };

        if (name) source.name = name;

        try {
            if (format === "json_pairs") {
                const text = refs.glossaryImportText ? refs.glossaryImportText.value : "";
                source.text = text;
            } else if (format === "csv" || format === "tsv"
                || format === "xliff" || format === "tbx" || format === "tmx") {
                const fileInput = refs.glossaryImportFile;
                if (fileInput && fileInput.files && fileInput.files[0]) {
                    source.inline_bytes_b64 = await fileToBase64(fileInput.files[0]);
                } else if (refs.glossaryImportText && refs.glossaryImportText.value) {
                    source.text = refs.glossaryImportText.value;
                } else {
                    setImportStatus("Provide a file or text content.", "error");
                    return;
                }
            } else if (format === "git_glossary") {
                source.git_url = refs.glossaryImportGitUrl
                    ? refs.glossaryImportGitUrl.value.trim() : "";
                if (!source.git_url) {
                    setImportStatus("Git URL is required.", "error");
                    return;
                }
                source.git_path = refs.glossaryImportGitPath
                    ? refs.glossaryImportGitPath.value.trim() || "GLOSSARY.md" : "GLOSSARY.md";
                source.git_ref = refs.glossaryImportGitRef
                    ? refs.glossaryImportGitRef.value.trim() || "HEAD" : "HEAD";
            } else if (format === "sql_table") {
                source.sql_dsn = refs.glossaryImportSqlDsn
                    ? refs.glossaryImportSqlDsn.value.trim() : "";
                source.sql_source_table = refs.glossaryImportSqlSourceTable
                    ? refs.glossaryImportSqlSourceTable.value.trim() : "";
                source.sql_target_table = refs.glossaryImportSqlTargetTable
                    ? refs.glossaryImportSqlTargetTable.value.trim() : "";
                source.sql_source_col = refs.glossaryImportSqlSourceCol
                    ? refs.glossaryImportSqlSourceCol.value.trim() || "source" : "source";
                source.sql_target_col = refs.glossaryImportSqlTargetCol
                    ? refs.glossaryImportSqlTargetCol.value.trim() || "target" : "target";
                source.sql_where = refs.glossaryImportSqlWhere
                    ? refs.glossaryImportSqlWhere.value.trim() : "";
                if (!source.sql_dsn || !source.sql_source_table) {
                    setImportStatus("DSN and source table are required.", "error");
                    return;
                }
            }

            setImportStatus("Importing…", "info");

            const channelId = window.localStorage
                ? window.localStorage.getItem("progress_channel_id") || null
                : null;
            const sessionToken = window.localStorage
                ? window.localStorage.getItem("progress_session_token") || null
                : null;

            const body = {
                source,
                channel_id: channelId,
                session_token: sessionToken,
            };

            const res = await fetch(IMPORT_ENDPOINT, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) {
                const detail = (data && data.detail) || res.statusText;
                setImportStatus(`Import failed: ${detail}`, "error");
                return;
            }
            if (data && data.queued) {
                setImportStatus(`Queued job ${data.job_id} for ${data.format}.`, "info");
            } else {
                setImportStatus(
                    `Imported ${data.entry_count} entries (${data.format}).`,
                    "success",
                );
            }
            await loadLibrary();
        } catch (err) {
            setImportStatus(`Import error: ${err.message}`, "error");
        }
    }

    async function saveTextareaGlossary() {
        const refs = getRefs();
        if (!refs) return;
        const textarea = refs.glossaryTextarea;
        const status = refs.glossaryStatus;
        const text = textarea ? textarea.value : "";
        const entries = readTextareaPairs(text);
        if (entries.length === 0) {
            if (status) status.textContent = "Nothing to save.";
            return;
        }
        try {
            const body = {
                source: {
                    format: "json_pairs",
                    text: JSON.stringify({ entries }),
                    name: "Inline glossary",
                },
            };
            const res = await fetch(IMPORT_ENDPOINT, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) {
                const detail = (data && data.detail) || res.statusText;
                if (status) status.textContent = `Save failed: ${detail}`;
                return;
            }
            if (status) {
                status.textContent = `Saved ${data.entry_count || entries.length} entries.`;
            }
            await loadLibrary();
        } catch (err) {
            if (status) status.textContent = `Save failed: ${err.message}`;
        }
    }

    function bindEvents() {
        const refs = getRefs();
        if (!refs) return;

        if (refs.glossaryImportBtn) {
            refs.glossaryImportBtn.addEventListener("click", openImportModal);
        }
        if (refs.glossaryImportCancel) {
            refs.glossaryImportCancel.addEventListener("click", closeImportModal);
        }
        if (refs.glossaryImportSubmit) {
            refs.glossaryImportSubmit.addEventListener("click", () => void submitImport());
        }
        if (refs.glossaryImportFormat) {
            refs.glossaryImportFormat.addEventListener("change", () => {
                showImportFormatGroups(refs.glossaryImportFormat.value);
            });
        }
        if (refs.glossaryPreviewBtn) {
            refs.glossaryPreviewBtn.addEventListener("click", () => void loadPreview());
        }
        if (refs.glossarySaveBtn) {
            refs.glossarySaveBtn.addEventListener("click", () => void saveTextareaGlossary());
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            bindEvents();
            void loadLibrary();
        });
    } else {
        bindEvents();
        void loadLibrary();
    }
})();