/// The talent's wallet (backend apps/money: wallet, payout account).
library;

import 'package:intl/intl.dart';

final _inr = NumberFormat.currency(locale: 'en_IN', symbol: '₹');

/// Whole paise as rupees: 447800 → ₹4,478.00.
String rupees(int paise) => _inr.format(paise / 100);

class PayoutAccount {
  const new({
    required this.method,
    required this.display,
    required this.status,
    required this.reason,
    required this.holdUntil,
  });

  factory fromJson(Map<String, Object?> json) => PayoutAccount(
    method: json['method'] as String? ?? '',
    display: json['display'] as String? ?? '',
    status: json['validation_status'] as String? ?? '',
    reason: json['validation_reason'] as String? ?? '',
    holdUntil: switch (json['hold_until']) {
      final String s => DateTime.parse(s),
      _ => null,
    },
  );

  final String method;
  final String display;

  /// pending, verified or failed.
  final String status;
  final String reason;
  final DateTime? holdUntil;

  bool get verified => status == 'verified';
  bool get pending => status == 'pending';
  bool get failed => status == 'failed';

  String get statusLabel => switch (status) {
    'verified' => 'Verified',
    'pending' => 'Being checked',
    'failed' => "Couldn't be verified",
    _ => 'Not linked',
  };
}

class Wallet {
  const new({
    required this.pending,
    required this.pendingNetEstimate,
    required this.available,
    required this.inTransit,
    required this.paidOut,
    required this.tdsThisYear,
    required this.financialYear,
    required this.account,
    required this.holdMessage,
    required this.canRequestPayout,
  });

  factory fromJson(Map<String, Object?> json) => Wallet(
    pending: _int(json['pending_paise']),
    pendingNetEstimate: _int(json['pending_net_estimate_paise']),
    available: _int(json['available_paise']),
    inTransit: _int(json['in_transit_paise']),
    paidOut: _int(json['paid_out_paise']),
    tdsThisYear: _int(json['tds_this_year_paise']),
    financialYear: json['financial_year'] as String? ?? '',
    account: switch (json['payout_account']) {
      final Map<String, Object?> a => PayoutAccount.fromJson(a),
      _ => null,
    },
    holdMessage: json['on_hold_message'] as String? ?? '',
    canRequestPayout: json['can_request_payout'] as bool? ?? false,
  );

  final int pending;
  final int pendingNetEstimate;
  final int available;
  final int inTransit;
  final int paidOut;
  final int tdsThisYear;
  final String financialYear;
  final PayoutAccount? account;
  final String holdMessage;
  final bool canRequestPayout;
}

int _int(Object? value) => (value as num?)?.toInt() ?? 0;

class WalletEntry {
  const new({
    required this.kind,
    required this.at,
    required this.amount,
    required this.status,
    required this.gigTitle,
    required this.gross,
    required this.commission,
    required this.commissionGst,
    required this.tds,
    required this.account,
    required this.failureReason,
  });

  factory fromJson(Map<String, Object?> json) => WalletEntry(
    kind: json['kind'] as String? ?? '',
    at: DateTime.parse(json['at']! as String),
    amount: _int(json['amount_paise']),
    status: json['status'] as String? ?? '',
    gigTitle: json['gig_title'] as String? ?? '',
    gross: _int(json['gross_paise']),
    commission: _int(json['commission_paise']),
    commissionGst: _int(json['commission_gst_paise']),
    tds: _int(json['tds_paise']),
    account: json['account'] as String? ?? '',
    failureReason: json['failure_reason'] as String? ?? '',
  );

  /// release or payout.
  final String kind;
  final DateTime at;
  final int amount;
  final String status;
  final String gigTitle;
  final int gross;
  final int commission;
  final int commissionGst;
  final int tds;
  final String account;
  final String failureReason;

  /// Barterly's commission and the GST on it.
  int get fees => commission + commissionGst;

  String get statusLabel => switch (status) {
    'processed' || 'settled' => 'Paid out',
    'processing' || 'sent' || 'sending' || 'creating' => 'On its way',
    'failed' => 'Failed',
    'reversed' => 'Returned by the bank',
    'on_hold' => 'On hold',
    'waiting_for_account' => 'Waiting for your payout account',
    'paused' => 'Paused',
    _ => 'Released to you',
  };
}

class HistoryPage {
  const new({required this.entries, required this.hasMore});

  final List<WalletEntry> entries;
  final bool hasMore;
}

/// Shape checks the server repeats (apps.money.payout_accounts).
abstract final class PayoutDetails {
  static final vpa = RegExp(
    r'^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9.\-]{1,63}$',
  );
  static final ifsc = RegExp(r'^[A-Z]{4}0[A-Z0-9]{6}$');
  static final accountNumber = RegExp(r'^[0-9]{9,18}$');

  static String? checkVpa(String value) => vpa.hasMatch(value.trim())
      ? null
      : "That doesn't look like a UPI id (name@bank).";

  static String? checkAccount(String value) =>
      accountNumber.hasMatch(value.replaceAll(RegExp(r'\s'), ''))
      ? null
      : 'An account number is 9 to 18 digits.';

  static String? checkIfsc(String value) =>
      ifsc.hasMatch(value.trim().toUpperCase())
      ? null
      : "That isn't an IFSC code (like HDFC0001234).";

  static String? checkName(String value) =>
      value.trim().length >= 2 ? null : 'Give the name on the account.';
}
