"""Profile / Bundle / Patch — high-level composition primitives for :class:`PluginContext`.

These three abstractions are the Phase 4 layer on top of the raw
``mount`` / ``register`` / ``swap`` primitives defined on
:class:`PluginContext`. They mirror the deepseek-harness / Cordis
"profile + bundle + patch" idiom:

- :class:`Bundle` is a named, reusable container of providers. Think
  of it as "the bundle of plugins that make the OCR pipeline work".
  Multiple bundles can be composed with ``+``.

- :class:`Patch` is a one-shot override: it swaps a single service
  registration for another implementation and restores the previous
  state on dispose. Patches are the right tool for "I need a sqlite
  log here, but the rest of the profile stays the same".

- :class:`Profile` is a named collection of bundles + patches.
  Loading a profile mounts every bundle and applies every patch,
  returning a single disposer that unwinds everything in reverse
  order. Profiles are the right tool for "spin up the default
  server config" / "spin up the test config".

The primitives compose. A bundle can include another bundle (via
``__add__`` or the constructor); a profile can include bundles
*and* patches. The :meth:`apply` method on each level is the
single integration point with the :class:`PluginContext`.

Why a separate module
---------------------

Keeping the high-level API in its own module makes the contract
explicit and testable without touching :mod:`plugin.context`. The
context only knows about ``register`` / ``swap`` / ``mount``;
profiles, bundles, and patches are pure data + a tiny apply
helper. A future phase can swap the apply helper for a different
runtime (e.g. an async variant for runtime plugin reloading)
without rewriting either side.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from omniscribe.api.plugin.context import Disposer, PluginContext

#: A :class:`Plugin` is a callable that takes a context and returns
#: a top-level disposer. Re-exported here for callers that want to
#: construct bundles without importing the deeper module.
Plugin = Callable[[PluginContext], Disposer]


@dataclass(frozen=True)
class Bundle:
    """A named, composable container of :class:`Plugin` providers.

    A bundle groups related providers under a single name so a
    profile can load the whole group with one call. Bundles are
    immutable and additive: ``bundle_a + bundle_b`` returns a new
    bundle whose name is the concatenation of the two and whose
    providers are the two providers concatenated in order.

    Parameters
    ----------
    name:
        Human-readable name. Used for diagnostics and for the
        combined-name when bundles are added together.
    providers:
        The :class:`Plugin` callables that comprise the bundle.
        Each one is mounted via :meth:`PluginContext.mount` when
        :meth:`apply` is called.
    description:
        Optional human-readable description. Diagnostic only.
    """

    name: str
    providers: tuple[Plugin, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(
                f"Bundle name must be a non-empty string, got {self.name!r}"
            )
        for i, p in enumerate(self.providers):
            if not callable(p):
                raise TypeError(
                    f"Bundle providers must be callables, got "
                    f"{type(p).__name__!r} at index {i}"
                )

    def __add__(self, other: Bundle) -> Bundle:
        """Compose two bundles into a new one.

        ``bundle_a + bundle_b`` is a left-to-right concatenation:
        ``bundle_a``'s providers run first, then ``bundle_b``'s.
        The combined name joins the two with ``"+"`` so it's
        diagnosable in profile listings.
        """
        if not isinstance(other, Bundle):
            return NotImplemented
        return Bundle(
            name=f"{self.name}+{other.name}",
            providers=self.providers + other.providers,
            description=(
                f"{self.description} + {other.description}".strip(" +")
                if self.description or other.description
                else ""
            ),
        )

    def apply(self, ctx: PluginContext) -> Disposer:
        """Mount every provider in this bundle into ``ctx``.

        Returns a single disposer that unwinds every provider in
        reverse mount order. The disposers from each individual
        :meth:`PluginContext.mount` call are collected and
        composed, so calling the returned disposer is equivalent
        to disposing the providers one by one in LIFO order.
        """
        disposers: list[Disposer] = []
        for provider in self.providers:
            disposers.append(ctx.mount(provider))
        return _compose_disposers(disposers, f"bundle:{self.name}")


@dataclass(frozen=True)
class Patch:
    """Swap a single service registration with a new implementation.

    A patch is the right tool for a one-off override: it leaves
    the rest of the context alone and only touches the slot at
    ``(protocol, name)``. On dispose the previous state is
    restored (or the slot is removed if nothing was registered
    before the patch).

    Internally, :meth:`apply` calls :meth:`PluginContext.swap`,
    which is the Phase 4 primitive that snapshots the previous
    state before overwriting.

    Parameters
    ----------
    protocol:
        The :class:`Protocol` class (or any class) that identifies
        the service slot. Used as the registry key alongside
        ``name``.
    impl:
        The new implementation. Must structurally satisfy
        ``protocol`` if the protocol is ``@runtime_checkable``.
    name:
        Slot name. Defaults to ``"default"`` to match the rest of
        the registration API.
    description:
        Optional human-readable description. Diagnostic only.
    """

    protocol: type
    impl: Any
    name: str = "default"
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(
                f"Patch name must be a non-empty string, got {self.name!r}"
            )
        if not isinstance(self.protocol, type):
            raise TypeError(
                f"Patch protocol must be a class, got {type(self.protocol).__name__!r}"
            )

    def apply(self, ctx: PluginContext) -> Disposer:
        """Apply the swap to ``ctx`` and return the restore disposer.

        The returned disposer unwinds the swap (restoring the
        previous impl or removing the new one) and is itself
        tracked by the context's effect scope, so a single
        :meth:`PluginContext.dispose` unwinds every active patch.
        """
        return ctx.swap(self.protocol, self.impl, name=self.name)


@dataclass(frozen=True)
class Profile:
    """A named, ready-to-load collection of bundles and patches.

    A profile is the highest-level primitive: it groups one or
    more :class:`Bundle` instances (the bulk of the setup) with
    zero or more :class:`Patch` instances (the surgical
    overrides). Loading a profile into a context mounts every
    bundle and applies every patch, returning one disposer that
    unwinds everything.

    Bundles are mounted first (so their services are available
    when the patches are applied); patches are applied after.
    Disposal happens in reverse: patches first, then bundles
    in reverse bundle order.

    Parameters
    ----------
    name:
        Human-readable name. Used for diagnostics and for
        the bookkeeping log line emitted by :meth:`apply`.
    bundles:
        The :class:`Bundle` instances to mount.
    patches:
        The :class:`Patch` instances to apply after the bundles.
    description:
        Optional human-readable description. Diagnostic only.
    """

    name: str
    bundles: tuple[Bundle, ...] = field(default_factory=tuple)
    patches: tuple[Patch, ...] = field(default_factory=tuple)
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(
                f"Profile name must be a non-empty string, got {self.name!r}"
            )
        for i, b in enumerate(self.bundles):
            if not isinstance(b, Bundle):
                raise TypeError(
                    f"Profile bundles must be Bundle instances, got "
                    f"{type(b).__name__!r} at index {i}"
                )
        for i, p in enumerate(self.patches):
            if not isinstance(p, Patch):
                raise TypeError(
                    f"Profile patches must be Patch instances, got "
                    f"{type(p).__name__!r} at index {i}"
                )

    def apply(self, ctx: PluginContext) -> Disposer:
        """Load the profile into ``ctx`` and return one disposer.

        The disposer unwinds every effect registered while loading
        this profile (bundles in reverse order, then patches in
        reverse order). Calling it leaves the context as it was
        before :meth:`apply` was called.
        """
        # Collect disposers in the order they're acquired. The
        # composite disposer walks them in REVERSE so the most
        # recently applied patch is undone first (matching LIFO
        # teardown semantics for a single-level swap).
        bundle_disposers: list[Disposer] = []
        for bundle in self.bundles:
            bundle_disposers.append(bundle.apply(ctx))
        patch_disposers: list[Disposer] = []
        for patch in self.patches:
            patch_disposers.append(patch.apply(ctx))
        # Bundle unwind happens first (LIFO within the bundle
        # chain), then patches LIFO. We reverse each list and
        # concatenate so the composite walks them in the right
        # order.
        ordered = list(reversed(bundle_disposers)) + list(reversed(patch_disposers))
        return _compose_disposers(ordered, f"profile:{self.name}")


def _compose_disposers(disposers: list[Disposer], label: str) -> Disposer:
    """Return a single disposer that walks ``disposers`` in order.

    A disposer that itself raises does NOT abort the rest of the
    chain — every remaining disposer still runs. The first
    exception (if any) is re-raised after the chain is exhausted
    so the caller sees something went wrong but every effect is
    still undone. This is the same fail-soft teardown contract
    that :class:`EffectScope` provides at the lower level; we
    keep it consistent here so a profile load with one broken
    provider still cleans up the rest.
    """
    if not disposers:
        return lambda: None

    def _composite() -> None:
        first_exc: BaseException | None = None
        # LIFO: the most-recently-registered disposer runs first so
        # teardown unwinds in the reverse order of construction.
        for d in reversed(disposers):
            try:
                d()
            except BaseException as exc:
                if first_exc is None:
                    first_exc = exc
        if first_exc is not None:
            # Re-raise the first failure so the caller can see it,
            # but every disposer has already been called.
            raise first_exc

    _composite.__name__ = f"dispose_{label}"  # for tracebacks
    return _composite


__all__ = ["Bundle", "Patch", "Plugin", "Profile"]
