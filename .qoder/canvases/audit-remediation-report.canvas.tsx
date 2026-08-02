import {
  Stack, Row, Grid, Divider, Text, H1, H2, H3,
  Stat, Table, Callout, CollapsibleSection,
  useHostTheme,
} from 'qoder/canvas';

export default function AuditRemediationReport() {
  const { tokens } = useHostTheme();

  return (
    <Stack gap={24}>
      <Stack gap={4}>
        <H1>LocalDeepL Audit Remediation Report</H1>
        <Text tone="secondary">
          Comprehensive codebase audit — 24 findings analyzed, 11 fixes implemented · August 2, 2026
        </Text>
      </Stack>

      {/* Summary Stats */}
      <Grid columns={4} gap={12}>
        <Stat value="24" label="Findings Analyzed" />
        <Stat value="11" label="Fixes Implemented" tone="success" />
        <Stat value="711" label="Tests Passing" tone="success" />
        <Stat value="14" label="Files Modified" />
      </Grid>

      <Divider />

      {/* Severity Breakdown */}
      <H2>Severity Breakdown</H2>
      <Table
        headers={['Severity', 'Total', 'Fixed', 'Analyzed Only', 'Status']}
        rows={[
          ['CRITICAL', '2', '2', '0', '✓ All resolved'],
          ['HIGH', '5', '4', '1 (H1 — architectural)', '✓ 80% resolved'],
          ['MEDIUM', '5', '1', '4', 'Recommendations provided'],
          ['LOW', '4', '1', '3', 'Recommendations provided'],
          ['INFO', '8', '3', '5', 'Recommendations provided'],
        ]}
        rowTone={['danger', 'warning', undefined, undefined, undefined]}
      />

      <Divider />

      {/* Critical Fixes */}
      <H2>Critical Fixes (C1–C2)</H2>
      <Stack gap={12}>
        <Callout tone="danger" title="C1 · Celery Worker Auth Bypass — FIXED">
          Removed cross-process is_authorized() checks from Celery tasks that always returned False
          in the worker process. Added session_token to TreeTranslationRequest schema. Passed
          channel_id and session_token from the async translation route to .delay(). Progress frames
          now flow correctly to WebSocket clients during background tasks.
        </Callout>
        <Callout tone="danger" title="C2 · API Keys in URL Query Params — FIXED">
          Moved API key transmission from URL query parameters to the X-API-Key HTTP header on both
          the backend (FastAPI Header parameter) and frontend (apiGet options.headers). Prevents
          credential exposure in server logs, proxy logs, browser history, and Referer headers.
        </Callout>
      </Stack>

      <Divider />

      {/* High Severity Fixes */}
      <H2>High Severity Fixes (H2–H5)</H2>
      <Table
        headers={['ID', 'Finding', 'Fix Applied', 'File(s)']}
        rows={[
          ['H2', 'Image decode outside semaphore', 'Lazy decode inside semaphore + per-page cache', 'hybrid.py'],
          ['H3', 'ASGI protocol violation', 'Drop ALL messages after overflow', 'security_middleware.py'],
          ['H4', 'Missing REDIS_URL in Docker', 'Added redis://redis:6379/0 to api + worker', 'compose.yaml'],
          ['H5', 'Event-loop blocking', 'Wrapped CPU-bound calls in asyncio.to_thread()', 'extraction.py, artifacts.py'],
        ]}
      />
      <Callout tone="warning" title="H1 · Eager Full-PDF Memory Loading — Deferred">
        Requires architectural refactoring to use convert_generator() with bounded batch streaming.
        Estimated 8h effort with integration testing. Detailed recommendation provided in analysis.
      </Callout>

      <Divider />

      {/* Additional Fixes */}
      <H2>Additional Fixes (M4, I2, I5, I6, L4)</H2>
      <Table
        headers={['ID', 'Category', 'Fix', 'File']}
        rows={[
          ['M4', 'Resource Leak', 'AsyncOpenAI client uses async with context manager', 'config.py'],
          ['I2', 'Accessibility', 'Removed maximum-scale=1.0, user-scalable=no (WCAG)', 'index.html'],
          ['I5', 'Docker Hygiene', 'Added --no-dev to uv sync (removes pytest/ruff/mypy)', 'Dockerfile'],
          ['I6', 'Deployment', 'Implemented GET /api/health readiness probe', 'server.py'],
          ['L4', 'Documentation', 'Added per-service auth tokens to .env.example', '.env.example'],
        ]}
      />

      <Divider />

      {/* Changed Files */}
      <CollapsibleSection title="14 Modified Files" defaultOpen={false}>
        <Table
          headers={['File', 'Finding(s)']}
          rows={[
            ['src/local_deepl/api/tasks.py', 'C1'],
            ['src/local_deepl/api/routers/translation.py', 'C1'],
            ['src/local_deepl/api/schemas/requests.py', 'C1'],
            ['src/local_deepl/api/routers/config.py', 'C2, M4'],
            ['frontend/src/lib/api/config.ts', 'C2'],
            ['src/local_deepl/core/workflows/hybrid.py', 'H2'],
            ['src/local_deepl/api/services/security_middleware.py', 'H3'],
            ['compose.yaml', 'H4'],
            ['src/local_deepl/api/routers/extraction.py', 'H5'],
            ['src/local_deepl/api/routers/artifacts.py', 'H5'],
            ['frontend/index.html', 'I2'],
            ['Dockerfile', 'I5'],
            ['src/local_deepl/server.py', 'I6'],
            ['.env.example', 'L4'],
          ]}
        />
      </CollapsibleSection>

      <Divider />

      {/* Verification */}
      <H2>Verification Evidence</H2>
      <Grid columns={2} gap={12}>
        <Stack gap={8}>
          <H3>Backend</H3>
          <Table
            headers={['Check', 'Result']}
            rows={[
              ['Ruff lint (8 files)', 'All checks passed'],
              ['Ruff format (8 files)', 'Already formatted'],
              ['pytest (full suite)', '711 passed, 0 failed'],
              ['Test duration', '139.72s'],
            ]}
          />
        </Stack>
        <Stack gap={8}>
          <H3>Frontend</H3>
          <Table
            headers={['Check', 'Result']}
            rows={[
              ['Vite build', '133 modules transformed'],
              ['Build time', '1.31s'],
              ['Output', '6 assets to static/'],
              ['TypeScript', 'No errors'],
            ]}
          />
        </Stack>
      </Grid>

      <Divider />

      {/* Remaining Work */}
      <CollapsibleSection title="Remaining Findings (Analyzed, Not Code-Changed)" defaultOpen={false}>
        <Table
          headers={['ID', 'Severity', 'Finding', 'Recommended Action']}
          rows={[
            ['H1', 'HIGH', 'Eager full-PDF memory loading', 'Refactor to convert_generator() with bounded batches (~8h)'],
            ['M1', 'MEDIUM', 'Sequential translation pipeline', 'Convert to async + asyncio.gather with ainvoke()'],
            ['M2', 'MEDIUM', 'Canvas render race condition', 'Add render generation counter for cancellation'],
            ['M3', 'MEDIUM', 'Missing ARIA roles', 'Add role=textbox aria-multiline=true if contenteditable exists'],
            ['M5', 'MEDIUM', 'Silent page failures', 'Inject error markers into DocumentResult'],
            ['L1', 'LOW', 'PDF.js typed as any', 'Import PDFDocumentProxy type'],
            ['L2', 'LOW', 'PIL handles not closed', 'Close source image after .convert()'],
            ['L3', 'LOW', 'API client abstraction bypass', 'Add returnFullResponse option to client.ts'],
            ['I1', 'INFO', '59+ broad except Exception', 'Narrow to specific types in hot paths'],
            ['I3', 'INFO', '13 untested modules', 'Prioritize block_tree, translation_tree, preprocessing'],
            ['I4', 'INFO', 'CI Python version gap', 'Add 3.12 to test.yml matrix'],
            ['I7', 'INFO', 'Svelte 4 store patterns', 'Gradual $state migration on touch'],
            ['I8', 'INFO', 'No responsive layout', 'Add Tailwind breakpoints + drawer sidebars'],
          ]}
        />
      </CollapsibleSection>

      <Divider />
      <Text tone="secondary" size="small">
        Generated from audit_report.md (2026-08-02) · YANGI principles applied · All changes maintain backward compatibility
      </Text>
    </Stack>
  );
}
