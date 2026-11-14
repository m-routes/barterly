import 'dart:io';

import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';

/// Where a picked file comes from.
enum PickSource { camera, gallery }

/// A file the person picked, kept on the device until it is uploaded.
class PickedFile {
  const new({
    required this.path,
    required this.name,
    required this.contentType,
    required this.sizeBytes,
  });

  final String path;
  final String name;
  final String contentType;
  final int sizeBytes;

  bool get isVideo => contentType.startsWith('video/');
}

/// Camera and gallery access, behind an interface so tests don't need the
/// platform plugin.
abstract interface class MediaPicker {
  Future<PickedFile?> pickPhoto(PickSource source);
  Future<PickedFile?> pickVideo(PickSource source);

  /// Reads a picked file for upload.
  Future<List<int>> read(String path);

  /// Deletes a file this picker kept (after upload or when removed).
  Future<void> discard(String path);
}

/// Content types the API accepts (backend apps/media/policy.py).
String? contentTypeFor(String name) {
  final lower = name.toLowerCase();
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.webp')) return 'image/webp';
  if (lower.endsWith('.mp4')) return 'video/mp4';
  if (lower.endsWith('.pdf')) return 'application/pdf';
  return null;
}

class UnsupportedFileType implements Exception {
  const new(this.name);
  final String name;

  @override
  String toString() => 'UnsupportedFileType($name)';
}

class ImagePickerMediaPicker implements MediaPicker {
  new([ImagePicker? picker]) : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  ImageSource _source(PickSource s) =>
      s == PickSource.camera ? ImageSource.camera : ImageSource.gallery;

  @override
  Future<PickedFile?> pickPhoto(PickSource source) async {
    // Re-encoded as JPEG at a sensible size: well under the 10 MB cap.
    final file = await _picker.pickImage(
      source: _source(source),
      maxWidth: 2400,
      maxHeight: 2400,
      imageQuality: 85,
      requestFullMetadata: false,
    );
    return file == null ? null : await _keep(file);
  }

  @override
  Future<PickedFile?> pickVideo(PickSource source) async {
    final file = await _picker.pickVideo(
      source: _source(source),
      maxDuration: const Duration(minutes: 2),
    );
    return file == null ? null : await _keep(file);
  }

  /// Copies the pick out of the plugin's temporary folder, so a draft queued
  /// offline still has its files after the app restarts.
  Future<PickedFile> _keep(XFile file) async {
    final type = contentTypeFor(file.name);
    if (type == null) throw UnsupportedFileType(file.name);
    final dir = Directory(
      '${(await getApplicationSupportDirectory()).path}/attachments',
    );
    await dir.create(recursive: true);
    final stamp = DateTime.now().microsecondsSinceEpoch;
    final kept = '${dir.path}/$stamp-${file.name}';
    await file.saveTo(kept);
    return PickedFile(
      path: kept,
      name: file.name,
      contentType: type,
      sizeBytes: await File(kept).length(),
    );
  }

  @override
  Future<List<int>> read(String path) => File(path).readAsBytes();

  @override
  Future<void> discard(String path) async {
    final file = File(path);
    if (file.existsSync()) await file.delete();
  }
}
