import 'package:flutter/material.dart';

/// Navigation tabs in the OmniScribe workspace.
enum AppTab {
  workstation(
    id: 'workstation',
    label: 'Workstation',
    testId: 'app-tab-btn-workstation',
    icon: Icons.document_scanner_outlined,
    selectedIcon: Icons.document_scanner,
    description: 'Document OCR and layout analysis workspace',
  ),
  translation(
    id: 'translation',
    label: 'Translation',
    testId: 'app-tab-btn-translation',
    icon: Icons.translate_outlined,
    selectedIcon: Icons.translate,
    description: 'Bilingual translation & terminology workbench',
  ),
  transcription(
    id: 'transcription',
    label: 'Transcription',
    testId: 'app-tab-btn-transcription',
    icon: Icons.graphic_eq_outlined,
    selectedIcon: Icons.graphic_eq,
    description: 'Speech-to-text audio and video transcription',
  ),
  extraction(
    id: 'extraction',
    label: 'Extraction',
    testId: 'app-tab-btn-extraction',
    icon: Icons.data_object_outlined,
    selectedIcon: Icons.data_object,
    description: 'Structured schema extraction and JSON parsing',
  ),
  glossary(
    id: 'glossary',
    label: 'Glossary',
    testId: 'app-tab-btn-glossary',
    icon: Icons.auto_stories_outlined,
    selectedIcon: Icons.auto_stories,
    description: 'Domain terminology dictionaries and TM repositories',
  ),
  jobs(
    id: 'jobs',
    label: 'Jobs',
    testId: 'app-tab-btn-jobs',
    icon: Icons.layers_outlined,
    selectedIcon: Icons.layers,
    description: 'Batch execution logs and background tasks',
  ),
  settings(
    id: 'settings',
    label: 'Settings',
    testId: 'app-tab-btn-settings',
    icon: Icons.tune_outlined,
    selectedIcon: Icons.tune,
    description: 'System configurations and LLM provider endpoints',
  );

  const AppTab({
    required this.id,
    required this.label,
    required this.testId,
    required this.icon,
    required this.selectedIcon,
    required this.description,
  });

  final String id;
  final String label;
  final String testId;
  final IconData icon;
  final IconData selectedIcon;
  final String description;
}
