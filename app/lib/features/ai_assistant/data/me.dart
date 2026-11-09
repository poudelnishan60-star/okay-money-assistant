import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';

@immutable
class Me {
  const Me({
    required this.id,
    required this.name,
    required this.balancePaisa,
    required this.balanceHidden,
  });

  factory Me.fromJson(Map<String, Object?> json) => Me(
    id: json.str('id'),
    name: json.str('name'),
    balancePaisa: json.integer('balance_paisa'),
    balanceHidden: json.boolean('balance_hidden'),
  );

  final String id;
  final String name;
  final int balancePaisa;
  final bool balanceHidden;

  String get firstName => name.split(' ').first;
}

class MeRepository {
  const MeRepository(this._api);
  final ApiClient _api;

  Future<Me> fetch() async => Me.fromJson((await _api.getJson('/me'))! as Map<String, Object?>);
}

final meRepositoryProvider = Provider<MeRepository>(
  (ref) => MeRepository(ref.watch(apiClientProvider)),
);

final meProvider = FutureProvider<Me>((ref) => ref.watch(meRepositoryProvider).fetch());
