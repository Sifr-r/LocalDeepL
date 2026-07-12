// --------------------------------------------------------------------------
// Page thumbnails with live status + confidence heatmap toggle
// --------------------------------------------------------------------------
//
// Subscribes to block_complete events on the WebSocket and updates per-page
// thumbnail state. Click a thumbnail to jump to that page; the central
// viewport exposes `renderWorkspacePage(N)` which we call directly.

function buildThumbnailStrip(totalPages) {
    const strip = document.getElementById('page-thumbnail-strip');
    if (!strip) return;
    strip.replaceChildren();
    for (let i = 0; i < totalPages; i++) {
        const cell = document.createElement('div');
        cell.className = 'page-thumb-cell thumb-pending';
        cell.dataset.pageIdx = String(i);
        cell.title = `Page ${i + 1}`;

        const canvasHolder = document.createElement('div');
        canvasHolder.className = 'page-thumb-canvas';
        canvasHolder.dataset.canvas = String(i);
        cell.appendChild(canvasHolder);

        const label = document.createElement('div');
        label.className = 'page-thumb-label';
        label.textContent = String(i + 1);
        cell.appendChild(label);

        cell.addEventListener('click', () => {
            if (typeof renderWorkspacePage === 'function') {
                renderWorkspacePage(i + 1);
            }
        });
        strip.appendChild(cell);
    }
    // Try to render mini previews if a PDF doc is available
    try {
        const pdfDoc = (typeof workspaceState !== 'undefined') ? workspaceState.pdfDoc : null;
        if (pdfDoc && typeof pdfDoc.getPage === 'function') {
            for (let i = 1; i <= totalPages; i++) {
                renderThumbPreview(pdfDoc, i);
            }
        }
    } catch (e) {
        // best-effort only
    }
}

async function renderThumbPreview(pdfDoc, pageNum) {
    try {
        const cell = document.querySelector(`.page-thumb-cell[data-page-idx="${pageNum - 1}"] .page-thumb-canvas`);
        if (!cell) return;
        const page = await pdfDoc.getPage(pageNum);
        const baseViewport = page.getViewport({ scale: 1.0 });
        const scale = Math.min(60 / baseViewport.width, 80 / baseViewport.height);
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement('canvas');
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.borderRadius = '4px';
        const ctx = canvas.getContext('2d');
        cell.replaceChildren(canvas);
        await page.render({ canvasContext: ctx, viewport }).promise;
    } catch (e) {
        // best-effort
    }
}

function markThumbnailState(pageIdx, state) {
    const cell = document.querySelector(`.page-thumb-cell[data-page-idx="${pageIdx}"]`);
    if (!cell) return;
    cell.classList.remove('thumb-pending', 'thumb-progress', 'thumb-done');
    cell.classList.add(`thumb-${state}`);
}

function markAllThumbnailsPending() {
    const cells = document.querySelectorAll('.page-thumb-cell');
    cells.forEach((c) => {
        c.classList.remove('thumb-progress', 'thumb-done');
        c.classList.add('thumb-pending');
    });
}

// Subscribe to custom events dispatched by app.js when a block lands.
window.addEventListener('ocr-block', (e) => {
    const { page_idx } = e.detail || {};
    if (typeof page_idx !== 'number') return;
    markThumbnailState(page_idx, 'progress');
});

window.addEventListener('ocr-page-complete', (e) => {
    const { page_idx } = e.detail || {};
    if (typeof page_idx !== 'number') return;
    markThumbnailState(page_idx, 'done');
});

// React to totalPages changes via a polling hook on workspaceState.
(function watchTotalPages() {
    let lastTotal = -1;
    setInterval(() => {
        if (typeof workspaceState === 'undefined') return;
        const total = workspaceState.totalPages || 0;
        if (total && total !== lastTotal) {
            lastTotal = total;
            buildThumbnailStrip(total);
        }
    }, 500);
})();

// Confidence heatmap toggle
function toggleConfidenceHeatmap(on) {
    if (typeof refs === 'undefined' || !refs.workspaceBboxSvg) return;
    refs.workspaceBboxSvg.classList.toggle('confidence-heatmap', !!on);
    // Trigger a redraw of the current page's overlay.
    if (typeof drawLayoutBboxes === 'function' &&
        typeof workspaceState !== 'undefined' &&
        workspaceState.lastViewport) {
        drawLayoutBboxes(workspaceState.currentPageIdx, workspaceState.lastViewport);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('confidence-heatmap-toggle');
    if (toggle) {
        toggle.addEventListener('change', (e) => {
            toggleConfidenceHeatmap(e.target.checked);
        });
    }
});
