/// The version of the terms and privacy policy this build shows and asks people
/// to accept. Keep it equal to the web's LEGAL_VERSION and the API's
/// PRIVACY_*_VERSION settings; the API refuses a version that isn't current.
const legalVersion = '2026-11-draft-1';

/// Paths of the public legal pages on the web site (AppConfig.webBaseUrl).
abstract final class LegalPaths {
  static const terms = '/legal/terms';
  static const privacy = '/legal/privacy';
  static const communityRules = '/legal/community-rules';
  static const refunds = '/legal/refunds';
  static const grievance = '/grievance';
}
