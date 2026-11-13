import 'package:flutter/foundation.dart';

/// The signed-in account, from GET /api/v1/me/.
@immutable
class User {
  const new({
    required this.id,
    required this.phone,
    required this.role,
    required this.profileComplete,
  });

  factory fromJson(Map<String, Object?> json) => User(
    id: json['id']! as String,
    phone: json['phone']! as String,
    role: UserRole.parse(json['role'] as String? ?? ''),
    profileComplete: json['profile_complete'] as bool? ?? false,
  );

  final String id;
  final String phone;
  final UserRole role;
  final bool profileComplete;

  @override
  bool operator ==(Object other) =>
      other is User &&
      other.id == id &&
      other.phone == phone &&
      other.role == role &&
      other.profileComplete == profileComplete;

  @override
  int get hashCode => Object.hash(id, phone, role, profileComplete);
}

/// `none` until the person picks a role (the API sends "").
enum UserRole {
  none,
  talent,
  vendor,
  admin;

  static UserRole parse(String value) => switch (value) {
    'talent' => talent,
    'vendor' => vendor,
    'admin' => admin,
    _ => none,
  };
}
