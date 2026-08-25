import 'package:flutter/material.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';

/// Server connection health status.
enum ServerHealth {
  online(
    label: 'Online',
    description: 'Connected to OmniScribe backend server',
  ),
  checking(
    label: 'Checking',
    description: 'Verifying server connection and endpoint latency',
  ),
  offline(
    label: 'Offline',
    description: 'Cannot reach backend server. Check host / port.',
  );

  const ServerHealth({
    required this.label,
    required this.description,
  });

  final String label;
  final String description;

  Color getColor(BuildContext context) {
    final colors = context.colors;
    switch (this) {
      case ServerHealth.online:
        return colors.success;
      case ServerHealth.checking:
        return colors.warning;
      case ServerHealth.offline:
        return colors.error;
    }
  }
}
