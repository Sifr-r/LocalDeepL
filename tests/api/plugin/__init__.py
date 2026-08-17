"""Tests for the plugin context foundation.

Covers the 8 main behaviors of :class:`PluginContext`:

1. Service registration / lookup
2. Multiple implementations under the same Protocol
3. Event dispatch in 4 modes (emit / parallel / serial / waterfall)
4. Reversible effects + LIFO disposal
5. Plugin mount + dispose
6. Context disposal is final (raises on post-dispose access)
7. Replace semantics
8. Listener prepending + introspection
"""
