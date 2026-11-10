import 'package:barterly/src/pay_model.dart';
import 'package:flutter/material.dart';

class BarterlyApp extends StatelessWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Barterly',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatelessWidget {
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Barterly')),
      body: ListView(
        children: [
          for (final model in PayModel.values)
            ListTile(
              key: ValueKey('pay-model-${model.name}'),
              title: Text(model.label),
              subtitle: Text(model.summary),
            ),
        ],
      ),
    );
  }
}
