// Regression test for Sprint 3 / H-2 audit fix: TabRibbon tab buttons and
// the theme toggle must expose ``Semantics(button: true)`` and the
// selection state (``Semantics(selected: ...)``) to screen readers.
//
// Before the fix, a screen reader announced the tab's visible text only
// ("Workstation") with no indication that it was the selected tab. The
// fix wraps the InkWell/GestureDetector body in a ``Semantics`` widget
// that explicitly sets ``button: true`` and ``selected: isSelected``.
//
// We use ``tester.getSemantics(...)`` to find the Semantics node and
// inspect its data via ``SemanticsNode.getSemanticsData()``. The
// assertions are scoped to the tab button only; the brand, provider
// pill, and other decorative widgets remain unlabeled for now (they
// are informational, not actionable).

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/core/enums/app_tab.dart';
import 'package:omniscribe_client/presentation/shell/shell_state.dart';
import 'package:omniscribe_client/presentation/shell/tab_ribbon.dart';

void main() {
  testWidgets(
      'TabRibbon exposes Semantics(button: true, selected: ...) for tabs',
      (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        // Override only the simple StateProviders. The SettingsNotifier
        // uses ConfigRepository (overridden below) to fetch its initial
        // config; for the bare TabRibbon render we don't actually call
        // ``load()``, so the notifier's ``build()`` returning
        // ``SettingsState.initial()`` is enough to satisfy the ribbon.
        overrides: [
          activeTabProvider.overrideWith((ref) => AppTab.workstation),
        ],
        child: const MaterialApp(
          home: Scaffold(body: TabRibbon()),
        ),
      ),
    );
    await tester.pump();

    final handle = tester.getSemantics(find.text('Workstation'));
    final node = handle.getSemanticsData();
    expect(node.hasFlag(SemanticsFlag.isButton), isTrue,
        reason:
            'tab button must be announced as a button to screen readers');
    expect(node.hasFlag(SemanticsFlag.isSelected), isTrue,
        reason:
            'active tab must be announced with the selected state');

    final settingsHandle = tester.getSemantics(find.text('Settings'));
    final settingsNode = settingsHandle.getSemanticsData();
    expect(settingsNode.hasFlag(SemanticsFlag.isButton), isTrue);
    expect(settingsNode.hasFlag(SemanticsFlag.isSelected), isFalse);
  });
}
