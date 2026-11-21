import 'package:barterly/src/api/api_error.dart';
import 'package:barterly/src/wallet/wallet_models.dart';
import 'package:dio/dio.dart';

/// The wallet and payout account over REST (backend apps/money).
class WalletRepository {
  new(this._dio);

  final Dio _dio;

  Future<Wallet> wallet() => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>('/api/v1/wallet/');
    return Wallet.fromJson(response.data!);
  });

  Future<HistoryPage> history({
    String kind = '',
    String financialYear = '',
    int page = 1,
  }) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/wallet/history/',
      queryParameters: {
        if (kind.isNotEmpty) 'kind': kind,
        if (financialYear.isNotEmpty) 'fy': financialYear,
        'page': page,
      },
    );
    final body = response.data!;
    return HistoryPage(
      entries: [
        for (final e in (body['results'] as List?) ?? const [])
          if (e is Map<String, Object?>) WalletEntry.fromJson(e),
      ],
      hasMore: body['next'] != null,
    );
  });

  /// Pays out what's available now. Returns how many payouts went out and the
  /// reasons any were held.
  Future<(int sent, Map<String, int> held)> requestPayout() => guardApi(
    () async {
      final response = await _dio.post<Map<String, Object?>>(
        '/api/v1/wallet/payout/',
      );
      final body = response.data!;
      return (
        (body['sent'] as num?)?.toInt() ?? 0,
        {
          for (final e in ((body['held_reasons'] as Map?) ?? const {}).entries)
            '${e.key}': (e.value as num).toInt(),
        },
      );
    },
  );

  /// Links (or replaces) the payout account. Full details go to the payout
  /// provider and are never kept on the phone or shown again.
  Future<PayoutAccount> linkUpi(String vpa) =>
      _link({'method': 'upi', 'vpa': vpa.trim()});

  Future<PayoutAccount> linkBank({
    required String accountNumber,
    required String ifsc,
    required String holderName,
  }) => _link({
    'method': 'bank',
    'account_number': accountNumber.replaceAll(RegExp(r'\s'), ''),
    'ifsc': ifsc.trim().toUpperCase(),
    'holder_name': holderName.trim(),
  });

  Future<PayoutAccount> _link(Map<String, Object?> body) => guardApi(() async {
    final response = await _dio.put<Map<String, Object?>>(
      '/api/v1/payout-account/',
      data: body,
    );
    return PayoutAccount.fromJson(response.data!);
  });
}
