import 'package:flutter/material.dart';
import 'package:omniscribe_client/models/document_view_model.dart';
import 'document_state.dart';

/// Inherited widget provider for DocumentStateNotifier
class DocumentProvider extends InheritedNotifier<DocumentStateNotifier> {
  const DocumentProvider({
    super.key,
    required DocumentStateNotifier notifier,
    required super.child,
  }) : super(notifier: notifier);

  static DocumentViewModel of(BuildContext context) {
    final provider =
        context.dependOnInheritedWidgetOfExactType<DocumentProvider>();
    assert(provider != null, 'No DocumentProvider found in context');
    return provider!.notifier!.state;
  }

  static DocumentStateNotifier notifierOf(BuildContext context,
      {bool listen = false}) {
    if (listen) {
      final provider =
          context.dependOnInheritedWidgetOfExactType<DocumentProvider>();
      assert(provider != null, 'No DocumentProvider found in context');
      return provider!.notifier!;
    } else {
      final provider =
          context.getInheritedWidgetOfExactType<DocumentProvider>();
      assert(provider != null, 'No DocumentProvider found in context');
      return provider!.notifier!;
    }
  }
}
