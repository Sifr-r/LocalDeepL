import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/data/providers/provider_notifier.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/config_repository.dart';
import 'package:omniscribe_client/data/repositories/provider_repository.dart';

class _MockProviderRepository extends Mock implements ProviderRepository {}

class _MockConfigRepository extends Mock implements ConfigRepository {}

void main() {
  late _MockProviderRepository repo;
  late _MockConfigRepository configRepo;

  setUp(() {
    repo = _MockProviderRepository();
    configRepo = _MockConfigRepository();
    // Default stubs for the Settings notifier's load() path. Task 4's
    // setActiveProvider test reaches into settingsStateProvider.load()
    // which calls configRepo.getConfig() + getModels(...). The Settings
    // notifier swallows those errors into state.error, so a throw is fine
    // here — we only need the call to NOT crash the test container.
    when(() => configRepo.getConfig())
        .thenThrow(StateError('test stub: configRepo not configured'));
    when(() => configRepo.getModels(namespace: any(named: 'namespace')))
        .thenThrow(StateError('test stub: configRepo not configured'));
  });

  ProviderContainer makeContainer() {
    return ProviderContainer(
      overrides: [
        providerRepositoryProvider.overrideWithValue(repo),
        configRepositoryProvider.overrideWithValue(configRepo),
      ],
    );
  }

  group('ProviderBrowserNotifier.build', () {
    test('returns ProviderBrowserState.initial() before any method call', () {
      final container = makeContainer();
      addTearDown(container.dispose);

      final state = container.read(providerBrowserProvider);
      expect(state.providers, isEmpty);
      expect(state.isFetching, isFalse);
      expect(state.error, isNull);
    });
  });

  group('ProviderBrowserNotifier.fetchProviders', () {
    test('populates providers list', () async {
      const presetA = ProviderPreset(
        id: 'openai',
        name: 'OpenAI',
        category: 'popular',
        description: 'GPT models',
        recommendedBaseUrl: 'https://api.openai.com/v1',
        defaultModel: 'gpt-4o',
      );
      const presetB = ProviderPreset(
        id: 'template-provider',
        name: 'Template',
        category: 'popular',
        description: 'Uses placeholder',
        recommendedBaseUrl: 'http://{host}/v1', // contains '{' -> skip auto-fetch
        defaultModel: 'm',
      );
      when(() => repo.getProviders()).thenAnswer((_) async => [presetA, presetB]);

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await notifier.fetchProviders();

      final state = container.read(providerBrowserProvider);
      expect(state.providers, [presetA, presetB]);
      expect(state.isFetching, isFalse);
      expect(state.error, isNull);
    });

    test('on failure populates error and clears isFetching', () async {
      when(() => repo.getProviders()).thenThrow(Exception('boom'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await notifier.fetchProviders();

      final state = container.read(providerBrowserProvider);
      expect(state.isFetching, isFalse);
      expect(state.providers, isEmpty);
      expect(state.error, contains('boom'));
    });
  });

  group('ProviderBrowserNotifier.fetchModelsForProvider', () {
    test('populates modelsMap and removes the id from loadingModelIds on success', () async {
      when(() => repo.getProviderModels(any())).thenAnswer(
        (_) async => const ProviderModelsResponse(models: ['m1', 'm2']),
      );

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await notifier.fetchModelsForProvider('openai');

      final state = container.read(providerBrowserProvider);
      expect(state.modelsMap['openai'], ['m1', 'm2']);
      expect(state.loadingModelIds.contains('openai'), isFalse);
    });

    test('is a no-op when the id is already in loadingModelIds (deduplicates concurrent calls)', () async {
      var callCount = 0;
      when(() => repo.getProviderModels(any())).thenAnswer((_) async {
        callCount += 1;
        // Hold the future open so we can observe the in-flight flag.
        await Future<void>.delayed(const Duration(milliseconds: 20));
        return const ProviderModelsResponse(models: ['m']);
      });

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      // Kick off two concurrent calls; the second should be deduped.
      final f1 = notifier.fetchModelsForProvider('openai');
      final f2 = notifier.fetchModelsForProvider('openai');
      await Future.wait([f1, f2]);

      expect(callCount, 1);
      expect(container.read(providerBrowserProvider).loadingModelIds.contains('openai'), isFalse);
    });

    test('removes the id from loadingModelIds even when the repo throws', () async {
      when(() => repo.getProviderModels(any())).thenThrow(Exception('boom'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await notifier.fetchModelsForProvider('openai');

      final state = container.read(providerBrowserProvider);
      expect(state.loadingModelIds.contains('openai'), isFalse);
      expect(state.modelsMap['openai'], isNull);
    });
  });
}
