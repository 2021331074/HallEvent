// EventHall Flutter mobile starter
// Place this file at apps/mobile/lib/main.dart in a Flutter project.
// Android emulator default API: http://10.0.2.2:8000/api/v1
// Override for your environment with:
// flutter run --dart-define=API_BASE_URL=https://your-staging-api.example/api/v1
//
// This is an early starter, not a production release. It implements sample
// discovery, a validated local inquiry draft, and an optional public spaces API
// fetch. It does not submit inquiries, authenticate users, process payments,
// manage reservations, persist drafts, or implement staff tools. Confirm the
// endpoint and response shape against your actual API before connecting it.
// HTTP access on Android/iOS may need platform configuration. Never enable
// cleartext HTTP for production; use TLS and appropriate platform policies.

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';

const apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000/api/v1',
);

void main() => runApp(const EventHallApp());

class EventHallApp extends StatelessWidget {
  const EventHallApp({super.key});

  @override
  Widget build(BuildContext context) {
    const green = Color(0xFF46634E);
    final colors = ColorScheme.fromSeed(
      seedColor: green,
      surface: const Color(0xFFF9F8F3),
    );
    return MaterialApp(
      title: 'EventHall',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: colors,
        scaffoldBackgroundColor: const Color(0xFFF9F8F3),
        fontFamily: 'sans-serif',
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFFF9F8F3),
          foregroundColor: Color(0xFF282C29),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: green,
            foregroundColor: Colors.white,
            minimumSize: const Size(48, 48),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
        ),
      ),
      home: const AppShell(),
    );
  }
}

class Space {
  const Space({required this.id, required this.name, required this.description, this.capacity});
  final String id;
  final String name;
  final String description;
  final int? capacity;

  factory Space.fromJson(Map<String, dynamic> json) {
    final capacityValue = json['capacity'];
    return Space(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? 'Unnamed space').toString(),
      description: (json['description'] ?? 'Ask the venue about this space.').toString(),
      capacity: capacityValue is num ? capacityValue.toInt() : null,
    );
  }
}

const sampleSpaces = <Space>[
  Space(id: 'ballroom', name: 'The Grand Ballroom', description: 'A graceful setting for your biggest celebrations.', capacity: 300),
  Space(id: 'salon', name: 'The Garden Salon', description: 'A light-filled space for thoughtful gatherings.', capacity: 120),
  Space(id: 'terrace', name: 'The Ivory Terrace', description: 'An intimate setting under an open sky.', capacity: 80),
];

class SpacesApi {
  Future<List<Space>> fetchSpaces() async {
    final client = HttpClient();
    try {
      final uri = Uri.parse('${apiBaseUrl.replaceAll(RegExp(r'/$'), '')}/spaces');
      final request = await client.getUrl(uri).timeout(const Duration(seconds: 10));
      request.headers.set(HttpHeaders.acceptHeader, 'application/json');
      final response = await request.close().timeout(const Duration(seconds: 10));
      if (response.statusCode != 200) {
        throw HttpException('API returned HTTP ${response.statusCode}', uri: uri);
      }
      final body = await response.transform(utf8.decoder).join().timeout(const Duration(seconds: 10));
      final decoded = jsonDecode(body);
      final dynamic items = decoded is List ? decoded : decoded is Map ? decoded['items'] : null;
      if (items is! List) throw const FormatException('Expected a list or an object containing items.');
      return items.map((e) {
        if (e is! Map) throw const FormatException('Expected space objects.');
        return Space.fromJson(Map<String, dynamic>.from(e));
      }).toList();
    } finally {
      client.close(force: true);
    }
  }
}

class AppShell extends StatefulWidget {
  const AppShell({super.key});
  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int index = 0;
  final screens = const [HomeScreen(), ExploreScreen(), MyEventScreen(), ProfileScreen()];

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(child: IndexedStack(index: index, children: screens)),
        bottomNavigationBar: NavigationBar(
          selectedIndex: index,
          onDestinationSelected: (value) => setState(() => index = value),
          destinations: const [
            NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
            NavigationDestination(icon: Icon(Icons.explore_outlined), selectedIcon: Icon(Icons.explore), label: 'Explore'),
            NavigationDestination(icon: Icon(Icons.calendar_month_outlined), selectedIcon: Icon(Icons.calendar_month), label: 'My Event'),
            NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Profile'),
          ],
        ),
      );
}

class Eyebrow extends StatelessWidget {
  const Eyebrow(this.text, {super.key});
  final String text;
  @override
  Widget build(BuildContext context) => Text(text.toUpperCase(), style: const TextStyle(color: Color(0xFF987B4D), fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 1.5));
}

class DisplayTitle extends StatelessWidget {
  const DisplayTitle(this.text, {super.key});
  final String text;
  @override
  Widget build(BuildContext context) => Text(text, style: const TextStyle(fontFamily: 'serif', fontSize: 35, height: 1.12, color: Color(0xFF282C29)));
}

class DemoNotice extends StatelessWidget {
  const DemoNotice({super.key, this.text = 'Prototype only · no live bookings or payments'});
  final String text;
  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(color: const Color(0xFFF2ECDD), borderRadius: BorderRadius.circular(12)),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.info_outline, size: 18, color: Color(0xFF886F46)),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 12, height: 1.5, color: Color(0xFF67583D))),),
        ]),
      );
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});
  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
        children: [
          Row(children: [
            const Icon(Icons.door_front_door_outlined, color: Color(0xFF987B4D), size: 30),
            const SizedBox(width: 10),
            const Text('EventHall', style: TextStyle(fontFamily: 'serif', fontSize: 27)),
            const Spacer(),
            IconButton(tooltip: 'About this prototype', onPressed: () => showAbout(context), icon: const Icon(Icons.info_outline)),
          ]),
          const SizedBox(height: 26),
          const DemoNotice(),
          const SizedBox(height: 28),
          const Eyebrow('A setting as special as your story'),
          const SizedBox(height: 14),
          const DisplayTitle('Beautiful occasions.\nEffortless beginnings.'),
          const SizedBox(height: 15),
          Text('Explore welcoming spaces and start planning an occasion to remember.', style: TextStyle(color: Colors.grey.shade700, height: 1.6)),
          const SizedBox(height: 24),
          Container(
            height: 200,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(22),
              gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFFE8DEC9), Color(0xFFC5B89D)]),
            ),
            child: const Center(child: Icon(Icons.celebration_outlined, size: 78, color: Color(0xFF8E7D5E), semanticLabel: 'Decorative celebration illustration')),
          ),
          const SizedBox(height: 10),
          Text('Illustrative placeholder — replace with approved venue photography.', style: TextStyle(fontSize: 11, color: Colors.grey.shade700)),
          const SizedBox(height: 24),
          FilledButton.icon(onPressed: () => openInquiry(context), icon: const Icon(Icons.edit_calendar_outlined), label: const Text('Start an inquiry draft')),
          const SizedBox(height: 12),
          const Text('A draft is not submitted and does not reserve a date.', textAlign: TextAlign.center, style: TextStyle(fontSize: 12, color: Color(0xFF777C73))),
          const SizedBox(height: 32),
          const Eyebrow('Made for meaningful moments'),
          const SizedBox(height: 12),
          const Text('Every detail, considered.', style: TextStyle(fontFamily: 'serif', fontSize: 25)),
          const SizedBox(height: 16),
          const FeatureLine(icon: Icons.meeting_room_outlined, title: 'Spaces for your occasion', subtitle: 'Explore illustrative rooms and capacities.'),
          const FeatureLine(icon: Icons.support_agent_outlined, title: 'A personal approach', subtitle: 'Staff approval is required before confirmation.'),
          const FeatureLine(icon: Icons.verified_outlined, title: 'Clear next steps', subtitle: 'A request or quote alone does not reserve a date.'),
        ],
      );
}

class FeatureLine extends StatelessWidget {
  const FeatureLine({super.key, required this.icon, required this.title, required this.subtitle});
  final IconData icon;
  final String title;
  final String subtitle;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(padding: const EdgeInsets.all(10), decoration: BoxDecoration(color: const Color(0xFFEDF1E9), borderRadius: BorderRadius.circular(12)), child: Icon(icon, color: const Color(0xFF46634E))),
          const SizedBox(width: 14),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontWeight: FontWeight.w600)), const SizedBox(height: 5), Text(subtitle, style: TextStyle(color: Colors.grey.shade700, fontSize: 12, height: 1.4))])),
        ]),
      );
}

class ExploreScreen extends StatefulWidget {
  const ExploreScreen({super.key});
  @override
  State<ExploreScreen> createState() => _ExploreScreenState();
}

class _ExploreScreenState extends State<ExploreScreen> {
  List<Space> spaces = sampleSpaces;
  bool loading = false;
  bool live = false;
  String? error;

  Future<void> loadApi() async {
    setState(() { loading = true; error = null; });
    try {
      final result = await SpacesApi().fetchSpaces();
      if (!mounted) return;
      setState(() { spaces = result; live = true; });
    } catch (_) {
      if (!mounted) return;
      setState(() { error = 'Could not load spaces. Check the API URL, network, and response contract, then retry.'; });
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.fromLTRB(24, 28, 24, 32),
        children: [
          const Eyebrow('Find your perfect setting'),
          const SizedBox(height: 10),
          const DisplayTitle('Make room for something wonderful.'),
          const SizedBox(height: 12),
          Text(live ? 'Showing spaces returned by the configured API.' : 'Illustrative spaces and capacities, not verified venue information.', style: TextStyle(color: Colors.grey.shade700, height: 1.5)),
          const SizedBox(height: 18),
          Wrap(spacing: 10, runSpacing: 10, children: [
            OutlinedButton.icon(onPressed: loading ? null : loadApi, icon: const Icon(Icons.sync), label: Text(loading ? 'Loading…' : 'Load from API')),
            if (live) OutlinedButton(onPressed: () => setState(() { spaces = sampleSpaces; live = false; error = null; }), child: const Text('Show samples')),
          ]),
          if (loading) const Padding(padding: EdgeInsets.symmetric(vertical: 18), child: LinearProgressIndicator()),
          if (error != null) Padding(padding: const EdgeInsets.symmetric(vertical: 12), child: DemoNotice(text: error!)),
          if (!loading && spaces.isEmpty) const Padding(padding: EdgeInsets.symmetric(vertical: 32), child: Text('No spaces are currently available to display.')),
          const SizedBox(height: 12),
          ...spaces.map((space) => SpaceCard(space: space)),
        ],
      );
}

class SpaceCard extends StatelessWidget {
  const SpaceCard({super.key, required this.space});
  final Space space;
  @override
  Widget build(BuildContext context) => Card(
        margin: const EdgeInsets.only(bottom: 16),
        elevation: 0,
        color: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18), side: const BorderSide(color: Color(0xFFE8E9E1))),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(Icons.meeting_room_outlined, color: Color(0xFF9A8055), size: 32),
            const SizedBox(height: 14),
            Text(space.name, style: const TextStyle(fontFamily: 'serif', fontSize: 23)),
            const SizedBox(height: 8),
            Text(space.description, style: TextStyle(color: Colors.grey.shade700, height: 1.5)),
            const SizedBox(height: 14),
            if (space.capacity != null) Text('Up to ${space.capacity} guests · confirm layout', style: const TextStyle(fontSize: 12, color: Color(0xFF526A53))),
            const SizedBox(height: 8),
            TextButton(onPressed: () => openInquiry(context, preferredSpace: space.name), child: const Text('Start an inquiry draft →')),
          ]),
        ),
      );
}

class MyEventScreen extends StatelessWidget {
  const MyEventScreen({super.key});
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(24), children: [
        const Eyebrow('Your occasion, in one place'), const SizedBox(height: 12),
        const DisplayTitle('Your next chapter starts here.'), const SizedBox(height: 20),
        const DemoNotice(text: 'Accounts, quotes, payment status and reservations are not connected in this starter.'),
        const SizedBox(height: 40), const Icon(Icons.event_available_outlined, size: 58, color: Color(0xFF9DAD96)), const SizedBox(height: 20),
        const Text('No connected events', textAlign: TextAlign.center, style: TextStyle(fontFamily: 'serif', fontSize: 25)),
        const SizedBox(height: 10), const Text('Once secure sign-in and the booking API are implemented, your events can appear here.', textAlign: TextAlign.center, style: TextStyle(height: 1.5, color: Color(0xFF727A70))),
      ]);
}

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(24), children: [
        const Eyebrow('Your profile'), const SizedBox(height: 12), const DisplayTitle('A little more about you.'),
        const SizedBox(height: 20), const DemoNotice(text: 'Secure sign-in, privacy settings and notification preferences are not implemented yet.'),
        const SizedBox(height: 20),
        ListTile(contentPadding: EdgeInsets.zero, leading: const Icon(Icons.lock_outline), title: const Text('Account security'), subtitle: const Text('Available after identity integration'), onTap: () => showAbout(context)),
        ListTile(contentPadding: EdgeInsets.zero, leading: const Icon(Icons.notifications_outlined), title: const Text('Notifications'), subtitle: const Text('Not configured in this starter'), onTap: () => showAbout(context)),
        ListTile(contentPadding: EdgeInsets.zero, leading: const Icon(Icons.info_outline), title: const Text('About the prototype'), onTap: () => showAbout(context)),
      ]);
}

void showAbout(BuildContext context) => showDialog<void>(context: context, builder: (context) => AlertDialog(
      title: const Text('About this starter'),
      content: const SingleChildScrollView(child: Text('This Flutter starter is a prototype. It does not authenticate, submit inquiries, process payments or confirm bookings. Do not enter real personal information. Production requires a secure backend, accessible flows, platform integrations, testing and owner approval.')),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
    ));

void openInquiry(BuildContext context, {String? preferredSpace}) => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => InquiryDraftScreen(preferredSpace: preferredSpace)));

class InquiryDraftScreen extends StatefulWidget {
  const InquiryDraftScreen({super.key, this.preferredSpace});
  final String? preferredSpace;
  @override
  State<InquiryDraftScreen> createState() => _InquiryDraftScreenState();
}

class _InquiryDraftScreenState extends State<InquiryDraftScreen> {
  final form = GlobalKey<FormState>();
  final guests = TextEditingController();
  final message = TextEditingController();
  DateTime? date;
  String eventType = 'Wedding';
  bool understood = false;

  @override
  void dispose() { guests.dispose(); message.dispose(); super.dispose(); }

  Future<void> pickDate() async {
    final now = DateTime.now();
    final selected = await showDatePicker(context: context, initialDate: date ?? now.add(const Duration(days: 30)), firstDate: DateTime(now.year, now.month, now.day), lastDate: DateTime(now.year + 3));
    if (selected != null && mounted) setState(() => date = selected);
  }

  void reviewDraft() {
    if (!(form.currentState?.validate() ?? false)) return;
    if (date == null || !understood) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Choose a date and acknowledge that this is only a draft.')));
      return;
    }
    final dateText = MaterialLocalizations.of(context).formatFullDate(date!);
    showDialog<void>(context: context, builder: (context) => AlertDialog(
          title: const Text('Draft reviewed, not sent'),
          content: SingleChildScrollView(child: Text('Occasion: $eventType\nDate: $dateText\nGuests: ${guests.text}\nSpace: ${widget.preferredSpace ?? 'Not selected'}\n\nThis information is only in memory. No inquiry was submitted and no date was reserved.')),
          actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Continue editing'))],
        ));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Inquiry draft')),
        body: SafeArea(child: Form(key: form, child: ListView(padding: const EdgeInsets.all(24), children: [
          const Eyebrow('Let’s begin your occasion'), const SizedBox(height: 12),
          const DisplayTitle('Tell us what you have in mind.'), const SizedBox(height: 18),
          const DemoNotice(text: 'This form is a local draft only. It does not submit an inquiry or check availability. Please do not enter real personal information.'),
          const SizedBox(height: 24),
          DropdownButtonFormField<String>(initialValue: eventType, decoration: const InputDecoration(labelText: 'Event type'), items: ['Wedding', 'Birthday', 'Corporate', 'Other celebration'].map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(), onChanged: (value) { if (value != null) setState(() => eventType = value); }),
          const SizedBox(height: 16),
          OutlinedButton.icon(onPressed: pickDate, icon: const Icon(Icons.calendar_today_outlined), label: Text(date == null ? 'Choose a preferred date' : MaterialLocalizations.of(context).formatMediumDate(date!))),
          const SizedBox(height: 16),
          TextFormField(controller: guests, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Number of guests'), validator: (v) { final n = int.tryParse(v ?? ''); return n == null || n < 1 ? 'Enter a positive guest count.' : null; }),
          const SizedBox(height: 16),
          TextFormField(controller: message, maxLines: 4, maxLength: 1000, decoration: const InputDecoration(labelText: 'Notes (optional)')),
          if (widget.preferredSpace != null) Padding(padding: const EdgeInsets.only(bottom: 14), child: Text('Preferred space: ${widget.preferredSpace}')),
          CheckboxListTile(contentPadding: EdgeInsets.zero, value: understood, onChanged: (v) => setState(() => understood = v ?? false), title: const Text('I understand this is not a submitted request or reservation.', style: TextStyle(fontSize: 13))),
          const SizedBox(height: 12), FilledButton(onPressed: reviewDraft, child: const Text('Review draft')),
        ]))),
      );
}

// Production next steps: generated OpenAPI client; Riverpod controllers and
// repositories; managed OIDC authorization code + PKCE and secure token storage;
// accessible quote acceptance; server-side allocation/approval/payment checks;
// verified app links, push token lifecycle and private document access; Android
// and iOS device, integration, accessibility and release testing.

// Compatibility: If your installed Flutter SDK does not support the
// DropdownButtonFormField initialValue parameter, use value instead. Record the
// chosen SDK version and test against it in CI.
