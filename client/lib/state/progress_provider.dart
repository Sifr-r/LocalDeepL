import 'package:flutter/material.dart';
import 'package:omniscribe_client/models/job_progress_state.dart';
import 'progress_state.dart';

/// Inherited widget provider for ProgressStateNotifier
class ProgressProvider extends InheritedNotifier<ProgressStateNotifier> {
  const ProgressProvider({
    super.key,
    required ProgressStateNotifier notifier,
    required super.child,
  }) : super(notifier: notifier);

  static JobProgressState of(BuildContext context) {
    final provider = context.dependOnInheritedWidgetOfExactType<ProgressProvider>();
    assert(provider != null, 'No ProgressProvider found in context');
    return provider!.notifier!.state;
  }

  static ProgressStateNotifier notifierOf(BuildContext context, {bool listen = false}) {
    if (listen) {
      final provider = context.dependOnInheritedWidgetOfExactType<ProgressProvider>();
      assert(provider != null, 'No ProgressProvider found in context');
      return provider!.notifier!;
    } else {
      final provider = context.getInheritedWidgetOfExactType<ProgressProvider>();
      assert(provider != null, 'No ProgressProvider found in context');
      return provider!.notifier!;
    }
  }
}
