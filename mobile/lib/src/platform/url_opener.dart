import 'package:url_launcher/url_launcher.dart';

/// Opens links outside the app's own screens.
abstract interface class UrlOpener {
  /// The OS's in-app browser (SFSafariViewController / Custom Tabs). Used for
  /// the KYC provider's hosted ID and selfie page: it keeps the camera
  /// permission prompts and the provider's own security in the browser.
  Future<bool> openInApp(Uri url);

  /// The default browser or app for the link.
  Future<bool> openExternal(Uri url);
}

class LauncherUrlOpener implements UrlOpener {
  const new();

  @override
  Future<bool> openInApp(Uri url) =>
      launchUrl(url, mode: LaunchMode.inAppBrowserView);

  @override
  Future<bool> openExternal(Uri url) =>
      launchUrl(url, mode: LaunchMode.externalApplication);
}
