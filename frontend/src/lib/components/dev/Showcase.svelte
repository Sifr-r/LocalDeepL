<script lang="ts">
  /**
   * Design system showcase. Renders every primitive, the color
   * tokens (light + dark), the type scale, and the radius scale
   * side-by-side so we can visually verify Phase 1+2 before
   * refactoring the real screens.
   *
   * This file is dev-only and can be removed once Phase 3 lands.
   */
  import Button from '../ui/Button.svelte';
  import Input from '../ui/Input.svelte';
  import Select from '../ui/Select.svelte';
  import Card from '../ui/Card.svelte';
  import Badge from '../ui/Badge.svelte';
  import SectionHeader from '../ui/SectionHeader.svelte';
  import Toggle from '../ui/Toggle.svelte';

  let inputValue = '';
  let selectValue = 'auto';
  let toggleValue = true;
</script>

<div class="bg-app text-foreground p-8 space-y-10 min-h-screen font-body">

  <!-- ============================== HEADER ============================== -->
  <header class="flex items-end justify-between border-b border-border pb-4">
    <div>
      <p class="section-header mb-1">Design System</p>
      <h1 class="font-display text-2xl font-bold">OmniScribe tokens + primitives</h1>
      <p class="text-sm text-foreground-muted mt-1">Phase 1+2 — the foundation the real screens will use next.</p>
    </div>
    <div class="flex gap-2">
      <Badge variant="success" dot>Phase 1+2 complete</Badge>
      <Badge variant="neutral">7 primitives</Badge>
    </div>
  </header>

  <!-- ============================== COLORS ============================== -->
  <section>
    <SectionHeader title="Color tokens" description="Indigo brand + neutral surfaces + semantic. All wired to Tailwind v4 @theme." />

    <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-16 bg-brand-500"></div>
        <div class="p-2 text-xs">
          <div class="font-mono">brand-500</div>
          <div class="text-foreground-muted">#6366f1</div>
        </div>
      </div>
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-16 bg-brand-600"></div>
        <div class="p-2 text-xs">
          <div class="font-mono">brand-600</div>
          <div class="text-foreground-muted">#4f46e5</div>
        </div>
      </div>
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-16 bg-card border-b border-border"></div>
        <div class="p-2 text-xs">
          <div class="font-mono">card</div>
          <div class="text-foreground-muted">surface 1</div>
        </div>
      </div>
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-16 bg-card-raised border-b border-border"></div>
        <div class="p-2 text-xs">
          <div class="font-mono">card-raised</div>
          <div class="text-foreground-muted">surface 2</div>
        </div>
      </div>
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-16 bg-muted border-b border-border"></div>
        <div class="p-2 text-xs">
          <div class="font-mono">muted</div>
          <div class="text-foreground-muted">hover</div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3">
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-12 bg-success/20 border-b border-border"></div>
        <div class="p-2 text-xs"><div class="font-mono">success</div></div>
      </div>
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-12 bg-warning/20 border-b border-border"></div>
        <div class="p-2 text-xs"><div class="font-mono">warning</div></div>
      </div>
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-12 bg-danger/20 border-b border-border"></div>
        <div class="p-2 text-xs"><div class="font-mono">danger</div></div>
      </div>
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-12 bg-foreground/5 border-b border-border flex items-center px-2 text-xs text-foreground">Aa</div>
        <div class="p-2 text-xs"><div class="font-mono">foreground</div></div>
      </div>
      <div class="rounded-md border border-border overflow-hidden">
        <div class="h-12 bg-foreground/5 border-b border-border flex items-center px-2 text-xs text-foreground-muted">Aa</div>
        <div class="p-2 text-xs"><div class="font-mono">foreground-muted</div></div>
      </div>
    </div>
  </section>

  <!-- ============================== TYPE SCALE ============================== -->
  <section>
    <SectionHeader title="Typography" description="Geist display + Inter body + JetBrains Mono for identifiers only." />

    <Card padding="lg">
      <div class="space-y-4">
        <div class="flex items-baseline gap-4">
          <span class="font-mono text-xs text-foreground-muted w-16">h1 / 24</span>
          <h1>The quick brown fox jumps</h1>
        </div>
        <div class="flex items-baseline gap-4">
          <span class="font-mono text-xs text-foreground-muted w-16">h2 / 20</span>
          <h2>The quick brown fox jumps</h2>
        </div>
        <div class="flex items-baseline gap-4">
          <span class="font-mono text-xs text-foreground-muted w-16">h3 / 18</span>
          <h3>The quick brown fox jumps</h3>
        </div>
        <div class="flex items-baseline gap-4">
          <span class="font-mono text-xs text-foreground-muted w-16">body / 14</span>
          <p class="text-sm">The quick brown fox jumps over the lazy dog. Body copy in Inter 14/20.</p>
        </div>
        <div class="flex items-baseline gap-4">
          <span class="font-mono text-xs text-foreground-muted w-16">caption</span>
          <p class="text-xs text-foreground-muted">The quick brown fox jumps over the lazy dog.</p>
        </div>
        <div class="flex items-baseline gap-4">
          <span class="font-mono text-xs text-foreground-muted w-16">mono</span>
          <code class="font-mono text-sm">artifact_id: tx-7b91f3a2, model: allenai/olmocr-2-7b</code>
        </div>
      </div>
    </Card>
  </section>

  <!-- ============================== BUTTONS ============================== -->
  <section>
    <SectionHeader title="Buttons" description="5 variants × 3 sizes. One component, all primary actions." />

    <Card padding="lg">
      <div class="space-y-4">
        <div>
          <p class="section-header mb-2">Variants</p>
          <div class="flex flex-wrap items-center gap-3">
            <Button variant="primary">Primary action</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="primary" loading>Loading</Button>
            <Button variant="primary" disabled>Disabled</Button>
          </div>
        </div>
        <div>
          <p class="section-header mb-2">Sizes</p>
          <div class="flex flex-wrap items-end gap-3">
            <Button size="sm">Small</Button>
            <Button size="md">Medium</Button>
            <Button size="lg">Large hero</Button>
          </div>
        </div>
        <div>
          <p class="section-header mb-2">Full width</p>
          <Button fullWidth size="lg">Start processing</Button>
        </div>
      </div>
    </Card>
  </section>

  <!-- ============================== FORM CONTROLS ============================== -->
  <section>
    <SectionHeader title="Form controls" description="Input, Select, Toggle. Identical focus ring + border state." />

    <Card padding="lg">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="space-y-4">
          <Input
            label="OCR API Base URL"
            placeholder="http://localhost:1234/v1"
            bind:value={inputValue}
            hint="OpenAI-compatible endpoint."
          />
          <Input
            label="OCR API Key"
            type="password"
            placeholder="sk-..."
            value=""
            hint="Stored server-side, never sent to the browser."
          />
          <Input
            label="With error"
            value="not a url"
            error="Must be a valid http(s) URL"
          />
        </div>
        <div class="space-y-4">
          <Select
            label="Pipeline Mode"
            bind:value={selectValue}
            options={[
              { value: 'auto', label: 'Auto (recommended)' },
              { value: 'hybrid', label: 'Hybrid (OCR + VLM)' },
              { value: 'grounded', label: 'Grounded BBox' }
            ]}
          />
          <div class="space-y-2">
            <p class="form-label">Preprocessing toggles</p>
            <div class="surface-inset p-3 space-y-1">
              <Toggle label="Orientation detection" bind:checked={toggleValue} />
              <Toggle label="Deskew image" checked={true} />
              <Toggle label="Denoise" checked={false} description="Reduces scanning noise before OCR." />
            </div>
          </div>
        </div>
      </div>
    </Card>
  </section>

  <!-- ============================== BADGES ============================== -->
  <section>
    <SectionHeader title="Badges" description="Status, counts, tags. One component, six semantic variants." />

    <Card padding="lg">
      <div class="space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <Badge variant="neutral">Neutral</Badge>
          <Badge variant="brand" dot>Brand</Badge>
          <Badge variant="success" dot>Completed</Badge>
          <Badge variant="warning" dot>Processing</Badge>
          <Badge variant="danger" dot>Failed</Badge>
          <Badge variant="info">Info</Badge>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Badge size="md" variant="success">High confidence</Badge>
          <Badge size="md" variant="warning">Pages 2, 5, 7</Badge>
          <Badge size="md" variant="neutral">v2.5</Badge>
        </div>
      </div>
    </Card>
  </section>

  <!-- ============================== CARDS + SECTION HEADERS ============================== -->
  <section>
    <SectionHeader title="Cards & section headers" description="The universal panel pattern. One Card, three variants." />

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card padding="md">
        <SectionHeader title="Pipeline settings" divider={false} />
        <p class="text-sm text-foreground-muted">Mode, processors, and preprocessor toggles live here.</p>
        <div slot="footer" class="flex justify-end">
          <Button size="sm" variant="primary">Apply</Button>
        </div>
      </Card>
      <Card variant="raised" padding="md">
        <SectionHeader title="Document metadata" divider={false} />
        <p class="text-sm text-foreground-muted">Confidence, page count, artifact ID, and extracted text preview.</p>
      </Card>
      <Card variant="inset" padding="md">
        <SectionHeader title="Bounding box" divider={false} />
        <p class="text-sm text-foreground-muted">Selected region on the page canvas.</p>
      </Card>
    </div>
  </section>

  <!-- ============================== MOCK WORKSTATION PANEL ============================== -->
  <section>
    <SectionHeader title="Workstation panel preview" description="A slice of how the left panel will look in Phase 4. Mock data only." />

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <Card padding="md">
        <div class="space-y-4">
          <SectionHeader title="Upload" divider={false} description="PDF, PNG, JPG, AVIF, TIFF — up to 50 MB." />
          <div class="rounded-md border-2 border-dashed border-border hover:border-brand transition-colors p-6 text-center">
            <p class="text-sm text-foreground">Drop document or click to browse</p>
            <p class="text-xs text-foreground-muted mt-1 font-mono">.pdf, .png, .jpg</p>
          </div>
        </div>

        <div slot="footer" class="space-y-4">
          <SectionHeader title="Pipeline settings" divider={false} />
          <div class="space-y-3">
            <Select
              label="Pipeline mode"
              options={[
                { value: 'hybrid', label: 'Hybrid (OCR + VLM)' },
                { value: 'grounded', label: 'Grounded BBox' }
              ]}
            />
            <div class="grid grid-cols-2 gap-3">
              <Select
                label="Dense mode"
                options={[
                  { value: 'auto', label: 'Auto' },
                  { value: 'on', label: 'On' },
                  { value: 'off', label: 'Off' }
                ]}
              />
              <Select
                label="Spellcheck"
                options={[
                  { value: 'none', label: 'None' },
                  { value: 'basic', label: 'Basic' }
                ]}
              />
            </div>
          </div>
          <Button fullWidth size="lg" variant="primary">Start processing</Button>
        </div>
      </Card>
    </div>
  </section>

  <footer class="pt-4 border-t border-border text-xs text-foreground-muted">
    <p>Phase 1+2 deliverable. Light + dark mode use the same scale. Real components are still using legacy tokens and will be migrated in Phases 3–6.</p>
  </footer>
</div>
