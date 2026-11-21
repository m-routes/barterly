import 'package:barterly/src/api/token_store.dart';
import 'package:barterly/src/wallet/wallet_models.dart';
import 'package:barterly/src/wallet/wallet_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../helpers.dart';

Map<String, Object?> walletJson({
  bool canPay = true,
  Map<String, Object?>? account,
  String hold = '',
}) => {
  ...emptyWallet,
  'pending_paise': 500000,
  'pending_net_estimate_paise': 447800,
  'available_paise': 447800,
  'in_transit_paise': 0,
  'paid_out_paise': 120000,
  'tds_this_year_paise': 5000,
  'payout_account':
      account ??
      {
        'method': 'upi',
        'display': 'as•••@okicici',
        'validation_status': 'verified',
        'validation_reason': '',
        'verified_at': '2026-11-01T10:00:00Z',
        'changed_at': null,
        'hold_until': null,
        'pan_on_file': true,
      },
  'on_hold_reason': hold.isEmpty ? '' : 'id_not_verified',
  'on_hold_message': hold,
  'can_request_payout': canPay,
};

Map<String, Object?> entryJson(String kind, {String status = 'processed'}) => {
  'kind': kind,
  'at': '2026-12-21T10:00:00Z',
  'amount_paise': 447800,
  'status': status,
  'booking_id': 'b1',
  'gig_title': 'Rooftop café reels',
  'gross_paise': 500000,
  'commission_paise': 40000,
  'commission_gst_paise': 7200,
  'tds_paise': 5000,
  'account': kind == 'payout' ? 'as•••@okicici' : '',
  'reference': 'UTR1',
  'failure_reason': '',
};

Future<void> openWallet(WidgetTester tester, FakeApi api) async {
  usePhoneScreen(tester);
  await pumpApp(tester, api: api, tokens: MemoryTokenStore(signedInTokens));
  await tester.tap(find.text('Wallet'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('balances, the payout account and history', (tester) async {
    final kinds = <String?>[];
    final api = talentApi({
      'GET /api/v1/wallet/': (_) => ok(walletJson()),
      'GET /api/v1/wallet/history/': (request) {
        final kind = request.queryParameters['kind'] as String?;
        kinds.add(kind);
        return ok({
          'count': 2,
          'next': null,
          'previous': null,
          'results': [
            if (kind != 'release') entryJson('payout'),
            if (kind != 'payout') entryJson('release', status: 'settled'),
          ],
        });
      },
    });
    await openWallet(tester, api);

    expect(find.byType(WalletScreen), findsOneWidget);
    expect(find.text('₹4,478.00'), findsWidgets); // available
    expect(find.text('₹5,000.00'), findsOneWidget); // held in escrow
    expect(find.textContaining('About ₹4,478.00 to you'), findsOneWidget);
    expect(find.text('as•••@okicici'), findsOneWidget);
    expect(find.text('Verified'), findsOneWidget);

    await tester.scrollUntilVisible(find.text('Payout'), 300);
    await tester.scrollUntilVisible(
      find.textContaining('− ₹472.00 commission and GST'),
      200,
    );
    await tester.tap(find.text('Payouts'));
    await tester.pumpAndSettle();
    expect(kinds.last, 'payout');
    expect(find.text('Rooftop café reels'), findsNothing);
  });

  testWidgets('pays out on demand, and explains a hold', (tester) async {
    var paid = false;
    final api = talentApi({
      'GET /api/v1/wallet/': (_) =>
          ok(paid ? walletJson(canPay: false) : walletJson()),
      'POST /api/v1/wallet/payout/': (_) {
        paid = true;
        return ok({'sent': 1, 'held': 0, 'held_reasons': <String, int>{}});
      },
    });
    await openWallet(tester, api);
    await tester.tap(find.text('Pay out ₹4,478.00 now'));
    await tester.pumpAndSettle();
    expect(find.text('Payout on its way.'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(
            find.widgetWithText(FilledButton, 'Pay out ₹4,478.00 now'),
          )
          .onPressed,
      isNull,
    );
  });

  testWidgets('a hold is explained and payout is off', (tester) async {
    final api = talentApi({
      'GET /api/v1/wallet/': (_) => ok(
        walletJson(
          canPay: false,
          hold: 'Verify your ID to get your first payout.',
        ),
      ),
    });
    await openWallet(tester, api);
    expect(
      find.text('Verify your ID to get your first payout.'),
      findsOneWidget,
    );
  });

  testWidgets('links a UPI id after checking it on the phone', (tester) async {
    Map<String, Object?>? sent;
    final api = talentApi({
      'GET /api/v1/wallet/': (_) =>
          ok({...walletJson(), 'payout_account': null}),
      'PUT /api/v1/payout-account/': (request) {
        sent = Map<String, Object?>.from(request.data as Map);
        return ok({
          'method': 'upi',
          'display': 'as•••@okicici',
          'validation_status': 'pending',
          'validation_reason': '',
          'verified_at': null,
          'changed_at': null,
          'hold_until': null,
          'pan_on_file': false,
        });
      },
    });
    await openWallet(tester, api);
    final add = find.text('Add payout account');
    await tester.scrollUntilVisible(add, 200);
    await tester.tap(add);
    await tester.pumpAndSettle();
    expect(find.byType(LinkAccountScreen), findsOneWidget);
    expect(
      find.textContaining('Only a masked version is kept'),
      findsOneWidget,
    );
    expect(find.textContaining('wait 24 hours'), findsNothing); // a first link

    await tester.enterText(
      find.widgetWithText(TextFormField, 'UPI id'),
      'asha',
    );
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(
      find.text("That doesn't look like a UPI id (name@bank)."),
      findsOneWidget,
    );
    expect(sent, isNull);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'UPI id'),
      'asha@okicici',
    );
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(sent, {'method': 'upi', 'vpa': 'asha@okicici'});
    expect(find.byType(LinkAccountScreen), findsNothing);
  });

  testWidgets('a bank account, and the 24-hour hold when changing', (
    tester,
  ) async {
    Map<String, Object?>? sent;
    final api = talentApi({
      'GET /api/v1/wallet/': (_) => ok(walletJson()),
      'PUT /api/v1/payout-account/': (request) {
        sent = Map<String, Object?>.from(request.data as Map);
        return ok({'method': 'bank', 'display': 'HDFC0001234 ••••9012'});
      },
    });
    await openWallet(tester, api);
    final change = find.text('Change account');
    await tester.scrollUntilVisible(change, 200);
    await tester.tap(change);
    await tester.pumpAndSettle();
    expect(find.textContaining('wait 24 hours after a change'), findsOneWidget);
    await tester.tap(find.text('Bank account'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Name on the account'),
      'Asha Rao',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Account number'),
      '1234 5678 9012',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'IFSC code'),
      'hdfc0001234',
    );
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(sent, {
      'method': 'bank',
      'account_number': '123456789012',
      'ifsc': 'HDFC0001234',
      'holder_name': 'Asha Rao',
    });
  });

  test('payout details are checked like the server does', () {
    expect(PayoutDetails.checkVpa('asha.rao-1@ybl'), isNull);
    expect(PayoutDetails.checkVpa('a@1bank'), isNotNull);
    expect(PayoutDetails.checkAccount('1234 5678 9012'), isNull);
    expect(PayoutDetails.checkAccount('12345'), isNotNull);
    expect(PayoutDetails.checkIfsc('hdfc0001234'), isNull);
    expect(PayoutDetails.checkIfsc('HDFC1001234'), isNotNull);
    expect(rupees(447800), '₹4,478.00');
  });
}
