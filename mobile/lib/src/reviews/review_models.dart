/// Reviews and reputation (backend apps/reviews).
library;

class CategoryScore {
  const new({required this.key, required this.label, required this.score});

  factory fromJson(Map<String, Object?> json) => CategoryScore(
    key: json['key'] as String? ?? '',
    label: json['label'] as String? ?? '',
    score: (json['score'] as num?)?.toInt() ?? 0,
  );

  final String key;
  final String label;
  final int score;
}

class StayReview {
  const new({
    required this.id,
    required this.rating,
    required this.categories,
    required this.text,
    required this.status,
    required this.authorName,
    required this.publishedAt,
    required this.reply,
  });

  factory fromJson(Map<String, Object?> json) => StayReview(
    id: json['id']! as String,
    rating: (json['rating'] as num?)?.toInt() ?? 0,
    categories: [
      for (final c in (json['categories'] as List?) ?? const [])
        if (c is Map<String, Object?>) CategoryScore.fromJson(c),
    ],
    text: json['text'] as String? ?? '',
    status: json['status'] as String? ?? '',
    authorName: json['author_name'] as String? ?? '',
    publishedAt: switch (json['published_at']) {
      final String s => DateTime.parse(s),
      _ => null,
    },
    reply: switch (json['reply']) {
      final Map<String, Object?> r => r['text'] as String? ?? '',
      _ => null,
    },
  );

  final String id;
  final int rating;
  final List<CategoryScore> categories;
  final String text;
  final String status;
  final String authorName;
  final DateTime? publishedAt;
  final String? reply;

  bool get published => status == 'published';
}

class BookingReviews {
  const new({
    required this.reviewing,
    required this.canReview,
    required this.windowClosesAt,
    required this.categoryLabels,
    required this.mine,
    required this.theirs,
    required this.theyHaveReviewed,
  });

  factory fromJson(Map<String, Object?> json) => BookingReviews(
    reviewing: json['reviewing'] as String? ?? 'host',
    canReview: json['can_review'] as bool? ?? false,
    windowClosesAt: switch (json['window_closes_at']) {
      final String s => DateTime.parse(s),
      _ => null,
    },
    categoryLabels: {
      for (final e in ((json['category_labels'] as Map?) ?? const {}).entries)
        '${e.key}': '${e.value}',
    },
    mine: switch (json['mine']) {
      final Map<String, Object?> r => StayReview.fromJson(r),
      _ => null,
    },
    theirs: switch (json['theirs']) {
      final Map<String, Object?> r => StayReview.fromJson(r),
      _ => null,
    },
    theyHaveReviewed: json['they_have_reviewed'] as bool? ?? false,
  );

  final String reviewing;
  final bool canReview;
  final DateTime? windowClosesAt;
  final Map<String, String> categoryLabels;
  final StayReview? mine;
  final StayReview? theirs;
  final bool theyHaveReviewed;
}

class Reputation {
  const new({
    required this.ratingAverage,
    required this.reviewCount,
    required this.completionRate,
    required this.responseMinutes,
    required this.badges,
  });

  factory fromJson(Map<String, Object?> json) => Reputation(
    ratingAverage: switch (json['rating_average']) {
      final String s => double.tryParse(s),
      final num n => n.toDouble(),
      _ => null,
    },
    reviewCount: (json['review_count'] as num?)?.toInt() ?? 0,
    completionRate: (json['completion_rate'] as num?)?.toInt(),
    responseMinutes: (json['response_minutes'] as num?)?.toInt(),
    badges: [
      for (final b in (json['badges'] as List?) ?? const [])
        if (b is Map) '${b['label']}',
    ],
  );

  final double? ratingAverage;
  final int reviewCount;
  final int? completionRate;
  final int? responseMinutes;
  final List<String> badges;
}

const reviewCategories = ['communication', 'accuracy', 'safety', 'reliability'];
