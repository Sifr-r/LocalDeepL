/**
 * Vitest setup — runs once per test file before the suite loads.
 *
 * jsdom 26 does not ship ``DOMMatrix`` (or several other modern DOM
 * primitives that ``pdfjs-dist`` and the Svelte preview store reach for
 * at module-evaluation time). Without these polyfills, importing
 * :file:`../lib/stores/pdfPreview.ts` from a unit test throws
 * ``ReferenceError: DOMMatrix is not defined`` before any assertion
 * runs. The polyfills below are no-ops when the runtime already
 * provides the constructor (Node 22+, real browsers, happy-dom).
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

// ``DOMMatrix`` is the most common offender. jsdom 26 leaves it
// undefined, but pdfjs-dist touches it at top level to register its
// canvas path helpers.
if (typeof (globalThis as any).DOMMatrix === 'undefined') {
  class DOMMatrixPolyfill {
    a = 1;
    b = 0;
    c = 0;
    d = 1;
    e = 0;
    f = 0;
    m11 = 1;
    m12 = 0;
    m13 = 0;
    m14 = 0;
    m21 = 0;
    m22 = 1;
    m23 = 0;
    m24 = 0;
    m31 = 0;
    m32 = 0;
    m33 = 1;
    m34 = 0;
    m41 = 0;
    m42 = 0;
    m43 = 0;
    m44 = 1;
    is2D = true;
    isIdentity = true;
    constructor(_init?: string | number[]) {
      // Values intentionally default to the identity matrix — pdfjs-dist
      // only reads shape, not the math, when probing the constructor.
    }
    multiplySelf(): DOMMatrixPolyfill { return this; }
    preMultiplySelf(): DOMMatrixPolyfill { return this; }
    translateSelf(): DOMMatrixPolyfill { return this; }
    scaleSelf(): DOMMatrixPolyfill { return this; }
    rotateSelf(): DOMMatrixPolyfill { return this; }
    flipXSelf(): DOMMatrixPolyfill { return this; }
    flipYSelf(): DOMMatrixPolyfill { return this; }
    skewXSelf(): DOMMatrixPolyfill { return this; }
    skewYSelf(): DOMMatrixPolyfill { return this; }
    invertSelf(): DOMMatrixPolyfill { return this; }
    multiply(): DOMMatrixPolyfill { return this; }
    flipX(): DOMMatrixPolyfill { return this; }
    flipY(): DOMMatrixPolyfill { return this; }
    translate(): DOMMatrixPolyfill { return this; }
    scale(): DOMMatrixPolyfill { return this; }
    rotate(): DOMMatrixPolyfill { return this; }
    rotateFromVectorSelf(): DOMMatrixPolyfill { return this; }
    rotateFromVector(): DOMMatrixPolyfill { return this; }
    skewX(): DOMMatrixPolyfill { return this; }
    skewY(): DOMMatrixPolyfill { return this; }
    inverse(): DOMMatrixPolyfill { return this; }
    transformPoint(p: { x: number; y: number }): { x: number; y: number; z: number; w: number } {
      return { x: p.x, y: p.y, z: 0, w: 1 };
    }
    toFloat32Array(): Float32Array { return new Float32Array(16); }
    toFloat64Array(): Float64Array { return new Float64Array(16); }
    toJSON(): any { return {}; }
    toString(): string { return 'matrix(1, 0, 0, 1, 0, 0)'; }
  }
  (globalThis as any).DOMMatrix = DOMMatrixPolyfill;
  (globalThis as any).DOMPoint = class DOMPoint {
    x: number; y: number; z: number; w: number;
    constructor(x = 0, y = 0, z = 0, w = 1) { this.x = x; this.y = y; this.z = z; this.w = w; }
  };
  (globalThis as any).DOMQuad = class DOMQuad {};
  (globalThis as any).DOMRect = class DOMRect {
    x: number; y: number; width: number; height: number;
    constructor(x = 0, y = 0, width = 0, height = 0) {
      this.x = x; this.y = y; this.width = width; this.height = height;
    }
  };
}

// Some jsdom 26 versions lack the structured ``Blob`` integration that
// pdfjs-dist's worker bootstrap checks for. Provide a minimal stub so
// the import chain succeeds in tests that never call into the renderer
// (the workstation test mocks the response body and never renders PDF
// pages).
if (typeof (globalThis as any).structuredClone === 'undefined') {
  (globalThis as any).structuredClone = (v: any) => JSON.parse(JSON.stringify(v));
}

// jsdom 26 does not implement ``URL.createObjectURL`` / ``revokeObjectURL``.
// The preview store and the export modal both reach for these on the
// happy path; tests mock the downstream calls but the synchronous file
// selection in the workstation test still triggers the unstubbed path.
// Provide a no-op counter so the calls succeed without surfacing
// ``TypeError: ... is not a function`` as unhandled rejections.
if (typeof URL.createObjectURL !== 'function') {
  let counter = 0;
  (URL as any).createObjectURL = (_obj: unknown) => {
    counter += 1;
    return `blob:test://${counter}`;
  };
  (URL as any).revokeObjectURL = (_url: string) => {
    /* no-op in tests */
  };
}

// jsdom does not implement ``HTMLCanvasElement.getContext`` (it requires
// the optional ``canvas`` npm package, which is not a project dep).
// The PageCanvas component paints pages onto a real canvas; in tests we
// hand it a no-op 2D context so the render path completes without
// spamming jsdom's "not implemented" warnings.
const noopContext: any = new Proxy(
  {
    canvas: { width: 0, height: 0 },
    fillStyle: '#000',
    strokeStyle: '#000',
    lineWidth: 1,
    font: '10px sans-serif',
    textBaseline: 'alphabetic',
    globalAlpha: 1,
    fillRect: () => undefined,
    clearRect: () => undefined,
    strokeRect: () => undefined,
    fillText: () => undefined,
    strokeText: () => undefined,
    measureText: () => ({ width: 0 }),
    drawImage: () => undefined,
    beginPath: () => undefined,
    closePath: () => undefined,
    moveTo: () => undefined,
    lineTo: () => undefined,
    stroke: () => undefined,
    fill: () => undefined,
    arc: () => undefined,
    save: () => undefined,
    restore: () => undefined,
    translate: () => undefined,
    rotate: () => undefined,
    scale: () => undefined,
    setTransform: () => undefined,
    transform: () => undefined,
    rect: () => undefined,
    createLinearGradient: () => ({ addColorStop: () => undefined }),
    createPattern: () => null,
    getImageData: () => ({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
    putImageData: () => undefined,
    createImageData: () => ({ data: new Uint8ClampedArray(4), width: 1, height: 1 })
  },
  {
    get(target, prop) {
      if (prop in target) return (target as any)[prop];
      // Any other method / property reads default to a no-op function so
      // the PDF.js render path can call into the context without
      // throwing.
      return () => undefined;
    },
    set(target, prop, value) {
      (target as any)[prop] = value;
      return true;
    }
  }
);

const originalGetContext = HTMLCanvasElement.prototype.getContext;
if (!originalGetContext.toString().includes('[native code]') && typeof originalGetContext === 'function') {
  // jsdom's getContext throws an explicit "not implemented" error. Wrap
  // it so calls in the test environment return the no-op context above
  // instead. The check on the stringified source prevents re-wrapping in
  // environments that ship a real implementation.
  HTMLCanvasElement.prototype.getContext = function (_type: string) {
    return noopContext;
  } as any;
}
