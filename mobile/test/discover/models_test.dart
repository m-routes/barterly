import 'package:barterly/src/discover/clustering.dart';
import 'package:barterly/src/discover/discovery_filters.dart';
import 'package:barterly/src/discover/gig.dart';
import 'package:barterly/src/pay_model.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fixtures.dart';

void main() {
  group('DiscoveryFilters', () {
    test('defaults ask for best fit only', () {
      expect(const DiscoveryFilters().toParams(), {'sort': 'best_fit'});
      expect(const DiscoveryFilters().isEmpty, isTrue);
    });

    test('lists become sorted comma values', () {
      final f = const DiscoveryFilters().copyWith(
        payModels: {PayModel.paid, PayModel.barter},
        roles: {RoleTemplate.volunteer},
        stayTypes: {StayType.privateRoom, StayType.dormBed},
        city: ' Goa ',
        query: 'yoga',
        startFrom: () => DateTime(2026, 12),
        startTo: () => DateTime(2026, 12, 31),
        womenFriendly: true,
        verifiedHosts: true,
        minStay: () => 30,
        sort: GigSort.newest,
      );
      expect(f.toParams(), {
        'compensation_model': 'barter,paid',
        'role': 'volunteer',
        'stay_type': 'dorm_bed,private_room',
        'city': 'Goa',
        'q': 'yoga',
        'start_from': '2026-12-01',
        'start_to': '2026-12-31',
        'women_friendly': true,
        'verified_hosts': true,
        'min_stay': 30,
        'sort': 'newest',
      });
      // Role, stay, city, dates, verified hosts and min stay: six.
      expect(f.sheetCount, 6);
    });

    test("distance sort and radius need a point, so they're dropped", () {
      final f = const DiscoveryFilters().copyWith(
        sort: GigSort.distance,
        radiusKm: () => 25,
      );
      expect(f.toParams(), {'sort': 'best_fit'});
      final near = f.copyWith(
        point: () => const SearchPoint(latitude: 15.3, longitude: 74.1),
      );
      expect(near.toParams(), {
        'latitude': 15.3,
        'longitude': 74.1,
        'radius_km': 25.0,
        'sort': 'distance',
      });
    });

    test('saved-search params round trip (lists or commas)', () {
      final f = DiscoveryFilters.fromParams(const {
        'compensation_model': ['barter', 'hybrid'],
        'role': 'volunteer,specialist',
        'start_from': '2026-12-01',
        'women_friendly': true,
        'latitude': 15.3,
        'longitude': 74.1,
        'radius_km': 10,
        'sort': 'distance',
      });
      expect(f.payModels, {PayModel.barter, PayModel.hybrid});
      expect(f.roles, {RoleTemplate.volunteer, RoleTemplate.specialist});
      expect(f.startFrom, DateTime(2026, 12));
      expect(f.sort, GigSort.distance);
      expect(DiscoveryFilters.fromParams(f.toParams()), f);
    });

    test('clearing the sheet keeps chips and search', () {
      final f = const DiscoveryFilters().copyWith(
        payModels: {PayModel.volunteer},
        query: 'chef',
        womenFriendly: true,
        verifiedHosts: true,
        city: 'Goa',
      );
      final cleared = f.clearSheet();
      expect(cleared.sheetCount, 0);
      expect(cleared.payModels, {PayModel.volunteer});
      expect(cleared.query, 'chef');
      expect(cleared.womenFriendly, isTrue);
    });
  });

  group('Gig', () {
    test('parses a discover card', () {
      final gig = Gig.fromJson(
        gigJson(
          model: 'hybrid',
          startDate: '2026-12-12',
          endDate: '2027-01-09',
        ),
      );
      expect(gig.payModel, PayModel.hybrid);
      expect(gig.fit.score, 92);
      expect(gig.fit.breakdown, hasLength(2));
      expect(gig.fit.breakdown[1].neutral, isTrue);
      expect(gig.property.location?.radiusM, 1500);
      expect(gig.workSummary, '4 hrs/day · 5 days/week');
      expect(gig.youGet, 'Dorm bed + all meals + ₹6,000/month');
      expect(gig.whenSummary, 'From 12 Dec · 2 slots');
      expect(gig.stayLength, 'At least 14 days from 12 Dec');
      expect(
        gig.deliverables.single.label,
        '2 × instagram story: tag the property',
      );
      // Detail-only fields are unknown, not empty.
      expect(gig.screeningQuestions, isNull);
    });

    test('a property without a location has no point', () {
      final gig = Gig.fromJson(gigJson(lat: null));
      expect(gig.property.location, isNull);
    });

    test('the detail adds questions but keeps the fit and property', () {
      final card = Gig.fromJson(gigJson());
      final full = card.mergeDetail({
        'id': 'g1',
        'property': 'p-g1',
        'description': 'Welcome guests',
        'screening_questions': ['Can you commit to the full dates?'],
        'fit': null,
      });
      expect(full.screeningQuestions, ['Can you commit to the full dates?']);
      expect(full.description, 'Welcome guests');
      expect(full.property.name, 'Pine Trail Hostel');
      expect(full.fit.score, 92, reason: "the card's score is kept");
    });

    test('a page survives the offline cache round trip', () {
      final original = GigPage.fromJson(
        page([gigJson(), gigJson(id: 'g2')], next: 'abc'),
      );
      final restored = GigPage.fromJson(original.toJson());
      expect([for (final g in restored.gigs) g.id], ['g1', 'g2']);
      expect(restored.nextCursor, 'abc');
      expect(restored.gigs.first.title, original.gigs.first.title);
    });
  });

  group('clusterByGrid', () {
    final points = <String, ({double latitude, double longitude})?>{
      'kasol-a': (latitude: 32.010, longitude: 77.315),
      'kasol-b': (latitude: 32.012, longitude: 77.318),
      'goa': (latitude: 15.01, longitude: 74.02),
      'nowhere': null,
    };

    List<Cluster<String>> at(double zoom) =>
        clusterByGrid(points.keys, pointOf: (k) => points[k], zoom: zoom);

    test('nearby gigs merge when zoomed out', () {
      final clusters = at(5);
      expect(clusters, hasLength(2));
      final kasol = clusters.firstWhere((c) => c.items.length == 2);
      expect(kasol.items, unorderedEquals(['kasol-a', 'kasol-b']));
      expect(kasol.latitude, closeTo(32.011, 1e-9));
      expect(kasol.longitude, closeTo(77.3165, 1e-9));
    });

    test('they split when zoomed in', () {
      expect(at(17).every((c) => c.isSingle), isTrue);
      expect(at(17), hasLength(3));
    });

    test('gigs without a location are left out', () {
      final all = [for (final c in at(5)) ...c.items];
      expect(all, isNot(contains('nowhere')));
    });

    test('projection matches Web Mercator at the origin', () {
      final p = projectToPixels(0, 0, 0);
      expect(p.x, closeTo(128, 1e-9));
      expect(p.y, closeTo(128, 1e-9));
    });
  });
}
