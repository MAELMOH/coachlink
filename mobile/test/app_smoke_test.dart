/// Smoke test for the app shell.
///
/// Replaces the generated `widget_test.dart`, which asserted on the Flutter counter
/// demo. That test would have gone red the moment `front` replaced `main.dart` with
/// the real app — a red CI caused purely by scaffolding, which trains everyone to
/// ignore red CI.
///
/// This one asserts only what stays true for any CoachLink build: the root widget
/// mounts, a `MaterialApp` is present, and the first frame renders without throwing.
/// It is deliberately shallow; the real coverage lives in the feature tests and in
/// `integration_test/`.
@TestOn('vm')
library;

import 'package:coachlink/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('app shell', () {
    testWidgets('mounts and renders a first frame without throwing', (tester) async {
      await tester.pumpWidget(const MyApp());
      expect(tester.takeException(), isNull);
    });

    testWidgets('provides a MaterialApp at the root', (tester) async {
      await tester.pumpWidget(const MyApp());
      expect(find.byType(MaterialApp), findsOneWidget);
    });

    testWidgets('declares a navigator so go_router can drive deep links',
        (tester) async {
      // The invitation flow arrives via a deep link (ARCHITECTURE.md §2.1), so the
      // shell must always expose a navigator for the router to attach to.
      await tester.pumpWidget(const MyApp());
      expect(find.byType(Navigator), findsWidgets);
    });
  });
}
