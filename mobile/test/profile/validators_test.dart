import 'package:barterly/src/profile/validators.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('date of birth (18+, counted in IST)', () {
    // 20:00 UTC on 13 Nov 2026 is already 14 Nov (01:30) in India.
    final now = DateTime.utc(2026, 11, 13, 20);

    test('today is the Indian date, not the device or UTC date', () {
      expect(todayInIndia(now), DateTime(2026, 11, 14));
    });

    test('someone turning 18 today in India is old enough', () {
      expect(validateDateOfBirth(DateTime(2008, 11, 14), now: now), isNull);
    });

    test('one day short of 18 is not', () {
      expect(
        validateDateOfBirth(DateTime(2008, 11, 15), now: now),
        'You must be at least 18 to join Barterly.',
      );
    });

    test('missing, future and implausible dates', () {
      expect(validateDateOfBirth(null, now: now), 'Enter your date of birth.');
      expect(
        validateDateOfBirth(DateTime(2027), now: now),
        "Date of birth can't be in the future.",
      );
      expect(
        validateDateOfBirth(DateTime(1920), now: now),
        'Enter a real date of birth.',
      );
    });

    test('the picker stops at the last date that is 18 today', () {
      expect(latestAdultBirthday(now), DateTime(2008, 11, 14));
      // 29 Feb has no match 18 years earlier: use 28 Feb.
      expect(
        latestAdultBirthday(DateTime.utc(2028, 2, 29, 6)),
        DateTime(2010, 2, 28),
      );
    });
  });

  group('phone numbers', () {
    test('normalises Indian numbers and keeps foreign ones', () {
      expect(normalizePhone('98765 43210'), '+919876543210');
      expect(normalizePhone('+91 98765-43210'), '+919876543210');
      expect(normalizePhone('09876543210'), '+919876543210');
      expect(normalizePhone('+44 20 7946 0958'), '+442079460958');
      expect(normalizePhone('12345'), isNull);
      expect(normalizePhone('+91 12345 67890'), isNull);
    });

    test('sign-in wants an Indian mobile', () {
      expect(validateMobileForSignIn('9876543210'), isNull);
      expect(validateMobileForSignIn(''), 'Enter your mobile number.');
      expect(
        validateMobileForSignIn('+442079460958'),
        'Enter a 10-digit Indian mobile number.',
      );
    });

    test("the emergency contact can't be your own number", () {
      const own = '+919876543210';
      expect(validateEmergencyPhone('+44 20 7946 0958', ownPhone: own), isNull);
      expect(
        validateEmergencyPhone('98765 43210', ownPhone: own),
        "Use someone else's number, not your own.",
      );
      expect(
        validateEmergencyPhone('', ownPhone: own),
        "Enter your emergency contact's phone number.",
      );
      expect(
        validateEmergencyPhone('123', ownPhone: own),
        'Enter a valid phone number.',
      );
    });
  });

  test('OTP is six digits', () {
    expect(validateOtp('123456'), isNull);
    expect(validateOtp('12345'), isNotNull);
  });

  test('Instagram handles, with or without @', () {
    expect(validateInstagram('@asha.paints'), isNull);
    expect(validateInstagram(''), isNull);
    expect(validateInstagram('not a handle'), isNotNull);
  });

  test('required text', () {
    expect(requiredText('  ', 'a bio', max: 10), 'Enter a bio.');
    expect(
      requiredText('x' * 11, 'a bio', max: 10),
      'Keep this under 10 characters.',
    );
  });
}
