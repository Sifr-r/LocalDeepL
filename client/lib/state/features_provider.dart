import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/repositories/features_repository.dart';
import 'package:omniscribe_client/services/api_client.dart';

final featuresRepositoryProvider = Provider<FeaturesRepository>((ref) {
  return FeaturesRepository(ApiClient());
});
