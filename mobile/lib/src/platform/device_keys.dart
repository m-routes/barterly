/// What the app keeps on the device for one account, by key. Keyed by user,
/// so a shared phone never shows or sends one person's data as another's.
abstract final class DeviceKeys {
  /// The last first page of discover (fit scores are personal).
  static String discoverCache(String userId) => 'discover.last_page.v1.$userId';

  /// Applications waiting to be sent.
  static String outbox(String userId) => 'applications.outbox.v1.$userId';

  /// Removed when the person signs out.
  static List<String> forUser(String userId) => [
    discoverCache(userId),
    outbox(userId),
  ];
}
