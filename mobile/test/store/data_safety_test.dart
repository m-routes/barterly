import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:yaml/yaml.dart';

/// Keeps the store privacy answers honest (docs/store-privacy.md): a new SDK or
/// a new data type in the iOS privacy manifest must be declared in
/// store/data_safety.json first.
void main() {
  final declared = jsonDecode(
    File('store/data_safety.json').readAsStringSync(),
  ) as Map<String, Object?>;
  final data = (declared['data']! as List).cast<Map<String, Object?>>();

  test('every app dependency is accounted for', () {
    final pubspec =
        loadYaml(File('pubspec.yaml').readAsStringSync()) as YamlMap;
    final dependencies = (pubspec['dependencies'] as YamlMap).keys.toSet();
    final sdks = (declared['sdks']! as Map).keys.toSet();
    expect(
      dependencies.difference(sdks),
      isEmpty,
      reason: 'Add these to "sdks" in store/data_safety.json',
    );
    expect(
      sdks.difference(dependencies),
      isEmpty,
      reason: 'Remove these from "sdks": no longer dependencies',
    );
  });

  test('the iOS privacy manifest declares exactly the Apple types', () {
    final manifest = File('ios/Runner/PrivacyInfo.xcprivacy')
        .readAsStringSync();
    final inManifest = RegExp(
      r'<string>(NSPrivacyCollectedDataType(?!Purpose)\w+)</string>',
    ).allMatches(manifest).map((m) => m.group(1)).toSet();
    final inJson = {
      for (final entry in data) (entry['apple']! as Map)['type'] as String,
    };
    expect(inManifest, inJson);
    expect(manifest, contains('<key>NSPrivacyTracking</key>\n\t<false/>'));
  });

  test('every entry names its Play type, purposes and where in the code', () {
    for (final entry in data) {
      final play = entry['play']! as Map;
      expect(play['category'], isA<String>(), reason: '${entry['id']}');
      expect(play['purposes'], isNotEmpty, reason: '${entry['id']}');
      expect(play['optional'], isA<bool>(), reason: '${entry['id']}');
      expect(entry['sources'], isNotEmpty, reason: '${entry['id']}');
    }
  });

  test('the Play listing fits the console limits', () {
    int length(String name) =>
        File('store/play/en-IN/$name').readAsStringSync().trim().runes.length;
    expect(length('title.txt'), lessThanOrEqualTo(30));
    expect(length('short_description.txt'), lessThanOrEqualTo(80));
    expect(length('full_description.txt'), lessThanOrEqualTo(4000));
    expect(length('release_notes.txt'), lessThanOrEqualTo(500));
  });
}
