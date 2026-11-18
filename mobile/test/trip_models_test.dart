import 'package:barterly/src/apply/application.dart';
import 'package:barterly/src/trips/trip_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('each status is a step on the tracker with what comes next', () {
    expect(tripProgress(ApplicationStatus.applied).done, 1);
    expect(tripProgress(ApplicationStatus.shortlisted).done, 2);
    expect(tripProgress(ApplicationStatus.interview).done, 3);
    expect(
      tripProgress(ApplicationStatus.offered).next,
      'Review the offer and answer.',
    );
    final signing = tripProgress(
      ApplicationStatus.confirmed,
      bookingStatus: 'signing',
    );
    expect((signing.done, signing.isOver), (4, false));
    expect(signing.next, contains('Sign the agreement'));
    expect(
      tripProgress(
        ApplicationStatus.confirmed,
        bookingStatus: 'confirmed',
      ).done,
      5,
    );
    expect(
      tripProgress(
        ApplicationStatus.confirmed,
        bookingStatus: 'delivering',
      ).done,
      6,
    );
    final done = tripProgress(
      ApplicationStatus.confirmed,
      bookingStatus: 'completed',
    );
    expect((done.done, done.isOver), (7, true));
  });

  test('ended trips say why', () {
    expect(tripProgress(ApplicationStatus.rejected).ended, 'Not selected');
    expect(tripProgress(ApplicationStatus.withdrawn).isOver, isTrue);
    expect(tripProgress(ApplicationStatus.expired).ended, 'The offer expired');
    expect(
      tripProgress(
        ApplicationStatus.confirmed,
        bookingStatus: 'cancelled',
      ).ended,
      'The booking was cancelled',
    );
  });

  test('the interview decides the next step while interviewing', () {
    Interview interview(InterviewStatus status) => Interview(
      id: 'i1',
      status: status,
      startsAtLabel: 'Fri 20 Nov, 4:00 pm',
    );
    String next(InterviewStatus s) =>
        tripProgress(ApplicationStatus.interview, interview: interview(s)).next;
    expect(next(InterviewStatus.proposed), 'Pick a time for your interview.');
    expect(
      next(InterviewStatus.scheduled),
      'Interview on Fri 20 Nov, 4:00 pm.',
    );
    expect(next(InterviewStatus.newTimesRequested), contains('new times'));
  });

  test('reads the API', () {
    final detail = ApplicationDetail.fromJson(const {
      'id': 'a1',
      'gig': 'g1',
      'gig_title': 'Front desk',
      'status': 'interview',
      'timeline': [
        {'status': 'applied', 'at': '2026-11-10T10:00:00Z', 'reason': ''},
        {
          'status': 'interview',
          'at': '2026-11-12T10:00:00Z',
          'reason': 'Loved your pitch',
        },
      ],
      'interview': {
        'id': 'i1',
        'status': 'proposed',
        'slots': [
          {
            'id': 7,
            'starts_at': '2026-11-20T10:30:00Z',
            'starts_at_ist': 'Fri 20 Nov, 4:00 pm',
          },
        ],
        'starts_at': null,
        'starts_at_ist': '',
        'duration_minutes': 30,
        'video_link': '',
        'note': '',
      },
    });
    expect(detail.timeline.map((t) => t.status), [
      ApplicationStatus.applied,
      ApplicationStatus.interview,
    ]);
    expect(detail.timeline.last.reason, 'Loved your pitch');
    expect(detail.interview!.needsAPick, isTrue);
    expect(detail.interview!.slots.single.label, 'Fri 20 Nov, 4:00 pm');
  });
}
