/// Form checks for the talent profile, matching the API's rules so people see
/// problems before they submit. The API checks everything again.
library;

const minAgeYears = 18;
const maxSkills = 15;
const maxLanguages = 10;

/// Today's date in India. The API counts ages in IST, so a phone set to another
/// time zone gets the same answer the server will.
DateTime todayInIndia([DateTime? now]) {
  final ist = (now ?? DateTime.now()).toUtc().add(
    const Duration(hours: 5, minutes: 30),
  );
  return DateTime(ist.year, ist.month, ist.day);
}

int ageOn(DateTime born, DateTime today) {
  final beforeBirthday =
      today.month < born.month ||
      (today.month == born.month && today.day < born.day);
  return today.year - born.year - (beforeBirthday ? 1 : 0);
}

/// The latest date of birth that is 18 today (in IST).
DateTime latestAdultBirthday([DateTime? now]) {
  final today = todayInIndia(now);
  final candidate = DateTime(today.year - minAgeYears, today.month, today.day);
  // 29 Feb rolls forward to 1 Mar in non-leap years; step back to 28 Feb.
  return candidate.month == today.month
      ? candidate
      : DateTime(candidate.year, candidate.month, 0);
}

String? validateDateOfBirth(DateTime? born, {DateTime? now}) {
  if (born == null) return 'Enter your date of birth.';
  final today = todayInIndia(now);
  if (born.isAfter(today)) return "Date of birth can't be in the future.";
  final age = ageOn(born, today);
  if (age < minAgeYears) return 'You must be at least 18 to join Barterly.';
  if (age > 100) return 'Enter a real date of birth.';
  return null;
}

String? requiredText(String? value, String label, {required int max}) {
  final text = value?.trim() ?? '';
  if (text.isEmpty) return 'Enter $label.';
  if (text.length > max) return 'Keep this under $max characters.';
  return null;
}

/// Phone numbers: Indian numbers without a code, or any number with +code.
/// Returns E.164, or null if it can't be a real number.
String? normalizePhone(String input) {
  final cleaned = input.replaceAll(RegExp(r'[\s\-().]'), '');
  if (cleaned.startsWith('+')) {
    final digits = cleaned.substring(1);
    if (!RegExp(r'^[1-9]\d{7,14}$').hasMatch(digits)) return null;
    if (digits.startsWith('91') && !_indianNumber(digits.substring(2))) {
      return null;
    }
    return '+$digits';
  }
  var digits = cleaned;
  if (digits.length == 12 && digits.startsWith('91')) {
    digits = digits.substring(2);
  } else if (digits.length == 11 && digits.startsWith('0')) {
    digits = digits.substring(1);
  }
  return _indianNumber(digits) ? '+91$digits' : null;
}

/// 10-digit mobiles (6-9…) and landlines with an STD code (2-5…).
bool _indianNumber(String digits) => RegExp(r'^[2-9]\d{9}$').hasMatch(digits);

/// An Indian mobile, for signing in (the OTP goes to it).
String? normalizeIndianMobile(String input) {
  final phone = normalizePhone(input);
  if (phone == null || !phone.startsWith('+91')) return null;
  return RegExp(r'^\+91[6-9]\d{9}$').hasMatch(phone) ? phone : null;
}

String? validateMobileForSignIn(String? value) {
  if (value == null || value.trim().isEmpty) return 'Enter your mobile number.';
  return normalizeIndianMobile(value) == null
      ? 'Enter a 10-digit Indian mobile number.'
      : null;
}

String? validateOtp(String? value) =>
    RegExp(r'^\d{6}$').hasMatch(value?.trim() ?? '')
    ? null
    : 'Enter the 6-digit code we sent you.';

String? validateEmergencyPhone(String? value, {required String ownPhone}) {
  if (value == null || value.trim().isEmpty) {
    return "Enter your emergency contact's phone number.";
  }
  final phone = normalizePhone(value);
  if (phone == null) return 'Enter a valid phone number.';
  if (phone == ownPhone) return "Use someone else's number, not your own.";
  return null;
}

String? validateInstagram(String? value) {
  final handle = (value ?? '').trim().replaceFirst(RegExp('^@'), '');
  if (handle.isEmpty) return null;
  return RegExp(r'^[A-Za-z0-9._]{1,30}$').hasMatch(handle)
      ? null
      : 'Enter an Instagram handle, e.g. @yourname';
}
