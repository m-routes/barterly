import 'package:barterly/src/api/api_error.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// A `major.minor.patch` version. Build numbers (`+12`) and pre-release tags
/// (`-rc1`) are ignored, as on the server (backend apps/appversions).
@immutable
class AppVersion implements Comparable<AppVersion> {
  const new(this.major, this.minor, this.patch);

  static AppVersion? parse(String? value) {
    final core = (value ?? '').trim().split('+').first.split('-').first;
    final match = RegExp(r'^(\d{1,4})\.(\d{1,4})\.(\d{1,4})$').firstMatch(core);
    if (match == null) return null;
    return AppVersion(
      int.parse(match.group(1)!),
      int.parse(match.group(2)!),
      int.parse(match.group(3)!),
    );
  }

  final int major;
  final int minor;
  final int patch;

  @override
  int compareTo(AppVersion other) => major != other.major
      ? major.compareTo(other.major)
      : minor != other.minor
      ? minor.compareTo(other.minor)
      : patch.compareTo(other.patch);

  bool operator <(AppVersion other) => compareTo(other) < 0;

  @override
  bool operator ==(Object other) =>
      other is AppVersion && compareTo(other) == 0;

  @override
  int get hashCode => Object.hash(major, minor, patch);

  @override
  String toString() => '$major.$minor.$patch';
}

/// This install: its version and the platform name the API knows it by.
@immutable
class InstalledApp {
  const new({
    required this.version,
    required this.buildNumber,
    required this.platform,
  });

  /// `1.4.2` (versionName / CFBundleShortVersionString).
  final String version;
  final String buildNumber;

  /// `android` or `ios`; empty elsewhere (tests, desktop), which the API
  /// never blocks.
  final String platform;
}

String platformName(TargetPlatform platform) => switch (platform) {
  TargetPlatform.android => 'android',
  TargetPlatform.iOS => 'ios',
  _ => '',
};

enum UpdateNeed { none, available, required }

/// What the API says about supported versions (GET /api/v1/app/version/, or
/// the details of a 426 `upgrade_required`).
@immutable
class UpdatePolicy {
  const new({
    required this.minimumVersion,
    required this.latestVersion,
    this.storeUrl = '',
    this.message = '',
  });

  factory fromJson(Map<String, Object?> json) => UpdatePolicy(
    minimumVersion: json['minimum_version'] as String? ?? '0.0.0',
    latestVersion:
        json['latest_version'] as String? ??
        json['minimum_version'] as String? ??
        '0.0.0',
    storeUrl: json['store_url'] as String? ?? '',
    message: json['message'] as String? ?? '',
  );

  final String minimumVersion;
  final String latestVersion;
  final String storeUrl;
  final String message;

  /// An unreadable version is never blocked, like on the server.
  UpdateNeed needFor(String installed) {
    final current = AppVersion.parse(installed);
    if (current == null) return UpdateNeed.none;
    final minimum = AppVersion.parse(minimumVersion);
    final latest = AppVersion.parse(latestVersion);
    if (minimum != null && current < minimum) return UpdateNeed.required;
    if (latest != null && current < latest) return UpdateNeed.available;
    return UpdateNeed.none;
  }
}

/// The API's error code for "this app version is no longer supported".
const upgradeRequiredCode = 'upgrade_required';

class VersionRepository {
  const new(this._dio);

  final Dio _dio;

  Future<UpdatePolicy> fetch(InstalledApp app) => guardApi(() async {
    final response = await _dio.get<Map<String, Object?>>(
      '/api/v1/app/version/',
      queryParameters: {'platform': app.platform, 'version': app.version},
    );
    return UpdatePolicy.fromJson(response.data!);
  });
}

/// Sends `X-Client-Platform` and `X-Client-Version` on every call, and reports
/// a 426 `upgrade_required` (backend apps/appversions/middleware.py), which any
/// endpoint answers once this version is below the minimum.
class ClientVersionInterceptor extends Interceptor {
  new({required this._installed, required this._onUpgradeRequired});

  final Future<InstalledApp> Function() _installed;
  final void Function(UpdatePolicy policy) _onUpgradeRequired;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    try {
      final app = await _installed();
      if (app.platform.isNotEmpty) {
        options.headers['X-Client-Platform'] = app.platform;
        options.headers['X-Client-Version'] = app.version;
      }
    } on Object {
      // Without the headers the call still goes through; the server only
      // checks apps that say which version they are.
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    final data = err.response?.data;
    if (err.response?.statusCode == 426 &&
        data is Map &&
        data['code'] == upgradeRequiredCode) {
      final details = data['details'];
      final map = details is Map
          ? Map<String, Object?>.from(details)
          : <String, Object?>{};
      _onUpgradeRequired(
        UpdatePolicy.fromJson({
          ...map,
          if (data['message'] is String) 'message': data['message'],
        }),
      );
    }
    handler.next(err);
  }
}
