import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

class UsageMonitor extends ChangeNotifier {
  static final UsageMonitor _instance = UsageMonitor._internal();

  factory UsageMonitor() => _instance;

  UsageMonitor._internal();

  // ==========================================================
  // ESTADO INTERNO
  // ==========================================================

  final Map<String, Duration> _stationTimes = {
    'general': Duration.zero,
    'neumatico': Duration.zero,
    'maquinados': Duration.zero,
    'robot': Duration.zero,
    'prensado': Duration.zero,
  };

  final Map<String, int> _stationProduction = {
    'general': 0,
    'neumatico': 0,
    'maquinados': 0,
    'robot': 0,
    'prensado': 0,
  };

  final Map<String, int> _stationFailures = {
    'general': 0,
    'neumatico': 0,
    'maquinados': 0,
    'robot': 0,
    'prensado': 0,
  };

  final Map<String, double> _stationConsumption = {
    'general': 0.0,
    'neumatico': 0.0,
    'maquinados': 0.0,
    'robot': 0.0,
    'prensado': 0.0,
  };

  final Map<String, bool> _isActive = {
    'general': false,
    'neumatico': false,
    'maquinados': false,
    'robot': false,
    'prensado': false,
  };

  final Map<String, int> _cycleFinishedPieces = {
    'general': 0,
    'neumatico': 0,
    'maquinados': 0,
    'robot': 0,
    'prensado': 0,
  };

  final Map<String, Map<String, int>> _componentInteractions = {
    'general': <String, int>{},
    'neumatico': <String, int>{},
    'maquinados': <String, int>{},
    'robot': <String, int>{},
    'prensado': <String, int>{},
  };

  int _pendingUsersCount = 0;

  Timer? _ticker;
  Timer? _consumptionTimer;
  StreamSubscription<QuerySnapshot<Map<String, dynamic>>>? _pendingUsersSub;

  bool _trackingStarted = false;
  bool _notificationScheduled = false;
  bool _isDisposed = false;

  // ==========================================================
  // GETTERS
  // ==========================================================

  int get pendingUsersCount => _pendingUsersCount;

  Duration getStationTime(String stationId) =>
      _stationTimes[stationId] ?? Duration.zero;

  int getStationProduction(String stationId) =>
      _stationProduction[stationId] ?? 0;

  int getStationFailures(String stationId) =>
      _stationFailures[stationId] ?? 0;

  double getStationConsumption(String stationId) =>
      _stationConsumption[stationId] ?? 0.0;

  int getCycleFinishedPieces(String stationId) =>
      _cycleFinishedPieces[stationId] ?? 0;

  bool isStationActive(String stationId) =>
      _isActive[stationId] ?? false;

  Duration get totalTime =>
      _stationTimes.values.fold(Duration.zero, (a, b) => a + b);

  int get totalProduction =>
      _stationProduction.values.fold(0, (a, b) => a + b);

  int get totalFailures =>
      _stationFailures.values.fold(0, (a, b) => a + b);

  double get totalConsumption =>
      _stationConsumption.values.fold(0.0, (a, b) => a + b);

  // ==========================================================
  // NOTIFICACIÓN SEGURA
  // ==========================================================

  /// Evita ejecutar notifyListeners() mientras Flutter está construyendo
  /// widgets. Si el framework está en fase build, la notificación se
  /// pospone hasta terminar el frame actual.
  void _safeNotifyListeners() {
    if (_isDisposed) return;

    final SchedulerPhase phase =
        SchedulerBinding.instance.schedulerPhase;

    final bool frameworkIsBuilding =
        phase == SchedulerPhase.persistentCallbacks ||
        phase == SchedulerPhase.midFrameMicrotasks;

    if (frameworkIsBuilding) {
      if (_notificationScheduled) return;

      _notificationScheduled = true;

      SchedulerBinding.instance.addPostFrameCallback((_) {
        _notificationScheduled = false;

        if (!_isDisposed) {
          notifyListeners();
        }
      });

      return;
    }

    notifyListeners();
  }

  // ==========================================================
  // INICIALIZACIÓN
  // ==========================================================

  void startTracking() {
    if (_trackingStarted || _isDisposed) return;

    _trackingStarted = true;

    // Se inicia fuera del constructor para evitar notificaciones mientras
    // MultiProvider todavía está construyendo su árbol.
    Future<void>.microtask(_initPendingUsersListener);

    _ticker = Timer.periodic(
      const Duration(seconds: 1),
      (_) {
        bool changed = false;

        _isActive.forEach((String station, bool active) {
          if (!active) return;

          _stationTimes[station] =
              (_stationTimes[station] ?? Duration.zero) +
                  const Duration(seconds: 1);

          changed = true;
        });

        if (changed) {
          _safeNotifyListeners();
        }
      },
    );

    _consumptionTimer = Timer.periodic(
      const Duration(seconds: 10),
      (_) {
        bool changed = false;

        _isActive.forEach((String station, bool active) {
          if (!active) return;

          _stationConsumption[station] =
              (_stationConsumption[station] ?? 0.0) + 0.05;

          changed = true;
        });

        if (changed) {
          _safeNotifyListeners();
        }
      },
    );
  }

  Future<void> _initPendingUsersListener() async {
    if (_isDisposed) return;

    await _pendingUsersSub?.cancel();

    _pendingUsersSub = FirebaseFirestore.instance
        .collection('usuarios')
        .where('rol', isEqualTo: 'Pendiente')
        .snapshots()
        .listen(
      (QuerySnapshot<Map<String, dynamic>> snapshot) {
        final int newCount = snapshot.docs.length;

        if (newCount == _pendingUsersCount) {
          return;
        }

        _pendingUsersCount = newCount;
        _safeNotifyListeners();
      },
      onError: (Object error, StackTrace stackTrace) {
        debugPrint(
          'Error escuchando usuarios pendientes: $error',
        );
      },
    );
  }

  // ==========================================================
  // ESTADO DE ESTACIONES
  // ==========================================================

  void setStationActive(String stationId, bool active) {
    if (!_isActive.containsKey(stationId)) {
      debugPrint(
        'UsageMonitor: estación desconocida: $stationId',
      );
      return;
    }

    // Evita reconstrucciones innecesarias.
    if (_isActive[stationId] == active) {
      return;
    }

    _isActive[stationId] = active;
    _safeNotifyListeners();
  }

  void addProduction(String stationId) {
    if (!_stationProduction.containsKey(stationId)) return;

    _stationProduction[stationId] =
        (_stationProduction[stationId] ?? 0) + 1;

    _cycleFinishedPieces[stationId] =
        (_cycleFinishedPieces[stationId] ?? 0) + 1;

    _safeNotifyListeners();

    unawaited(syncStationAuditoria(stationId));
  }

  void addFailure(String stationId) {
    if (!_stationFailures.containsKey(stationId)) return;

    _stationFailures[stationId] =
        (_stationFailures[stationId] ?? 0) + 1;

    _safeNotifyListeners();

    unawaited(syncStationAuditoria(stationId));
  }

  void incrementComponentInteraction(
    String stationId,
    String type,
    String componentId,
  ) {
    final Map<String, int>? interactions =
        _componentInteractions[stationId];

    if (interactions == null) return;

    final String key = '${type}_$componentId';

    interactions[key] = (interactions[key] ?? 0) + 1;

    _safeNotifyListeners();

    unawaited(syncStationAuditoria(stationId));
  }

  void resetCyclePieces(String stationId) {
    if (!_cycleFinishedPieces.containsKey(stationId)) return;

    if (_cycleFinishedPieces[stationId] == 0) return;

    _cycleFinishedPieces[stationId] = 0;
    _safeNotifyListeners();
  }

  // ==========================================================
  // FIRESTORE
  // ==========================================================

  Future<void> logEvent({
    required String maqueta,
    required String message,
    required String role,
    required String type,
  }) async {
    try {
      final SharedPreferences prefs =
          await SharedPreferences.getInstance();

      final String userName =
          prefs.getString('userName') ?? 'Usuario Desconocido';

      await FirebaseFirestore.instance
          .collection('historial')
          .add({
        'timestamp': FieldValue.serverTimestamp(),
        'maqueta': maqueta,
        'message': message,
        'role': role,
        'userName': userName,
        'type': type,
      });
    } catch (e, stackTrace) {
      debugPrint('Error al guardar log: $e');
      debugPrintStack(stackTrace: stackTrace);
    }
  }

  Future<void> syncStationAuditoria(String stationId) async {
    final Map<String, int>? interactions =
        _componentInteractions[stationId];

    if (interactions == null) return;

    try {
      final String timestamp = DateTime.now()
          .toIso8601String()
          .replaceAll(':', '-');

      await FirebaseFirestore.instance
          .collection('maquetas')
          .doc(stationId)
          .collection('auditoria')
          .doc(timestamp)
          .set({
        // Se crea una copia para evitar modificar el mapa mientras
        // Firestore lo está serializando.
        'componentes': Map<String, int>.from(interactions),
        'parosEmergencia': _stationFailures[stationId] ?? 0,
        'piezasProcesadas': _stationProduction[stationId] ?? 0,
        'ultimoReset':
            DateFormat('dd/MM/yyyy HH:mm:ss').format(DateTime.now()),
        'timestamp': FieldValue.serverTimestamp(),
      });
    } catch (e, stackTrace) {
      debugPrint(
        'Error al sincronizar auditoría de $stationId: $e',
      );
      debugPrintStack(stackTrace: stackTrace);
    }
  }

  // ==========================================================
  // UTILIDADES
  // ==========================================================

  String formatDuration(Duration duration) {
    String twoDigits(int number) =>
        number.toString().padLeft(2, '0');

    final String hours = twoDigits(duration.inHours);
    final String minutes =
        twoDigits(duration.inMinutes.remainder(60));
    final String seconds =
        twoDigits(duration.inSeconds.remainder(60));

    return '$hours:$minutes:$seconds';
  }

  // ==========================================================
  // LIBERACIÓN DE RECURSOS
  // ==========================================================

  @override
  void dispose() {
    if (_isDisposed) return;

    _isDisposed = true;
    _trackingStarted = false;

    _pendingUsersSub?.cancel();
    _pendingUsersSub = null;

    _ticker?.cancel();
    _ticker = null;

    _consumptionTimer?.cancel();
    _consumptionTimer = null;

    super.dispose();
  }
}
