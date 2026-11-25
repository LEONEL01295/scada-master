import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

class PlateHandler extends ChangeNotifier {
  final String ip;
  final int port;
  final String label;

  Socket? _socket;
  StreamSubscription<List<int>>? _subscription;

  Timer? _heartbeat;
  Timer? _reconnectTimer;

  final StringBuffer _buffer = StringBuffer();

  bool conectado = false;
  bool conectando = false;
  bool reconexionAutomatica = true;

  bool _disposed = false;
  bool _cerrando = false;

  int sent = 0;
  int received = 0;
  int lost = 0;
  int latencia = 0;

  DateTime? _pingSentAt;

  Map<String, dynamic> telemetry = {};

  final Map<String, Completer<Map<String, dynamic>>> _pending = {};

  PlateHandler({
    required this.ip,
    this.port = 8080,
    required this.label,
  });

  Future<bool> connect() async {
    if (_disposed || conectado || conectando) {
      return conectado;
    }

    conectando = true;
    _cerrando = false;
    _notify();

    try {
      await _closeSocket();

      final socket = await Socket.connect(
        ip,
        port,
        timeout: const Duration(seconds: 3),
      );

      if (_disposed || _cerrando) {
        socket.destroy();
        conectando = false;
        return false;
      }

      _socket = socket;
      _buffer.clear();

      _subscription = socket.listen(
        _onData,
        onError: (error) {
          debugPrint('$label error TCP: $error');
          _onDisconnect();
        },
        onDone: _onDisconnect,
        cancelOnError: false,
      );

      conectado = true;
      conectando = false;

      _startHeartbeat();
      _notify();

      debugPrint('$label conectado a $ip:$port');

      return true;
    } catch (error) {
      debugPrint('$label error de conexión: $error');

      conectado = false;
      conectando = false;

      _scheduleReconnect();
      _notify();

      return false;
    }
  }

  void _startHeartbeat() {
    _heartbeat?.cancel();

    _heartbeat = Timer.periodic(
      const Duration(seconds: 3),
          (_) {
        if (!conectado) return;

        _pingSentAt = DateTime.now();

        send({
          'comando': 'ping',
        });
      },
    );
  }

  void _onData(List<int> data) {
    if (_disposed) return;

    received++;

    _buffer.write(utf8.decode(data, allowMalformed: true));

    String contenido = _buffer.toString();

    while (contenido.contains('\n')) {
      final index = contenido.indexOf('\n');

      final linea = contenido.substring(0, index).trim();

      contenido = contenido.substring(index + 1);

      if (linea.isEmpty) continue;

      try {
        final decoded = jsonDecode(linea);

        if (decoded is Map<String, dynamic>) {
          _processResponse(decoded);
        }
      } catch (error) {
        debugPrint('$label JSON inválido: $error');
      }
    }

    _buffer
      ..clear()
      ..write(contenido);

    if (_buffer.length > 8192) {
      _buffer.clear();
      lost++;
    }

    _notify();
  }

  void _processResponse(Map<String, dynamic> response) {
    final comando = response['comando'];

    if (comando == 'pong') {
      if (_pingSentAt != null) {
        latencia = DateTime.now()
            .difference(_pingSentAt!)
            .inMilliseconds;

        _pingSentAt = null;
      }
    }

    final id = response['id'];

    if (id != null) {
      final completer = _pending.remove(id.toString());

      if (completer != null && !completer.isCompleted) {
        completer.complete(response);
      }
    }

    telemetry = {
      ...telemetry,
      ...response,
    };

    debugPrint('$label respuesta: $response');

    _notify();
  }

  bool send(Map<String, dynamic> command) {
    if (!conectado || _socket == null) {
      lost++;
      _notify();

      debugPrint('$label: placa desconectada');

      return false;
    }

    try {
      _socket!.write('${jsonEncode(command)}\n');

      sent++;

      _notify();

      return true;
    } catch (error) {
      lost++;

      debugPrint('$label error enviando: $error');

      _notify();

      return false;
    }
  }

  Future<Map<String, dynamic>?> sendAndWait(
      Map<String, dynamic> command, {
        Duration timeout = const Duration(seconds: 10),
      }) async {
    if (!conectado || _socket == null) {
      return null;
    }

    final id = '${DateTime.now().microsecondsSinceEpoch}';

    final completer = Completer<Map<String, dynamic>>();

    _pending[id] = completer;

    final message = {
      ...command,
      'id': id,
    };

    if (!send(message)) {
      _pending.remove(id);
      return null;
    }

    try {
      return await completer.future.timeout(timeout);
    } on TimeoutException {
      _pending.remove(id);
      lost++;

      debugPrint('$label: tiempo de espera agotado para $id');

      _notify();

      return null;
    }
  }

  void _onDisconnect() {
    if (_disposed || _cerrando) return;

    _heartbeat?.cancel();

    conectado = false;
    conectando = false;

    _socket = null;
    _subscription = null;

    _completePending();

    _notify();

    _scheduleReconnect();
  }

  void _completePending() {
    for (final completer in _pending.values) {
      if (!completer.isCompleted) {
        completer.complete({
          'status': 'error',
          'message': 'Conexión perdida',
        });
      }
    }

    _pending.clear();
  }

  void _scheduleReconnect() {
    if (_disposed ||
        _cerrando ||
        !reconexionAutomatica ||
        _reconnectTimer?.isActive == true) {
      return;
    }

    _reconnectTimer = Timer(
      const Duration(seconds: 2),
      () {
        if (!_disposed && !_cerrando && !conectado) {
          connect();
        }
      },
    );
  }

  Future<void> disconnect() async {
    _cerrando = true;

    _heartbeat?.cancel();
    _reconnectTimer?.cancel();

    conectado = false;
    conectando = false;

    _completePending();

    await _closeSocket();

    _notify();
  }

  Future<void> _closeSocket() async {
    await _subscription?.cancel();

    _subscription = null;

    try {
      _socket?.destroy();
    } catch (_) {}

    _socket = null;
  }

  void _notify() {
    if (!_disposed) {
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _cerrando = true;

    _heartbeat?.cancel();
    _reconnectTimer?.cancel();

    _subscription?.cancel();

    try {
      _socket?.destroy();
    } catch (_) {}

    _socket = null;

    _completePending();

    super.dispose();
  }
}

class MqttPlacasService extends ChangeNotifier {
  late final PlateHandler placa1;
  late final PlateHandler placa2;

  MqttPlacasService() {
    placa1 = PlateHandler(
      ip: '192.168.4.1',
      port: 8080,
      label: 'Placa 1',
    );

    placa2 = PlateHandler(
      ip: '192.168.4.10',
      port: 8080,
      label: 'Placa 2',
    );

    placa1.addListener(_notify);
    placa2.addListener(_notify);
  }

  bool get conectado => placa1.conectado || placa2.conectado;

  bool get ambasConectadas =>
      placa1.conectado && placa2.conectado;

  int get paquetesEnviados => placa1.sent + placa2.sent;
  int get paquetesRecibidos => placa1.received + placa2.received;
  int get paquetesPerdidos => placa1.lost + placa2.lost;

  String get latencia {
    if (!conectado) return '--';
    final conectadas = (placa1.conectado ? 1 : 0) + (placa2.conectado ? 1 : 0);
    if (conectadas == 0) return '--';
    final avg = (placa1.latencia + placa2.latencia) ~/ conectadas;
    return '$avg ms';
  }

  Future<void> conectar() async {
    await Future.wait([
      placa1.connect(),
      placa2.connect(),
    ]);
  }

  Future<void> desconectar() async {
    await Future.wait([
      placa1.disconnect(),
      placa2.disconnect(),
    ]);
  }

  Future<void> conectarPlaca1() async {
    await placa1.connect();
  }

  Future<void> conectarPlaca2() async {
    await placa2.connect();
  }

  Future<void> desconectarPlaca1() async {
    await placa1.disconnect();
  }

  Future<void> desconectarPlaca2() async {
    await placa2.disconnect();
  }

  void enviarComando(
    dynamic comandoOrAccion, [
    String? maqueta,
    dynamic target,
  ]) {
    if (comandoOrAccion is Map<String, dynamic>) {
      final m = comandoOrAccion['maqueta']?.toString().toLowerCase();

      if (m == 'robot' ||
          m == 'prensado' ||
          m == 'placa1') {
        placa1.send(comandoOrAccion);
        return;
      }

      if (m == 'neumatico' ||
          m == 'maquinados' ||
          m == 'placa2') {
        placa2.send(comandoOrAccion);
        return;
      }

      debugPrint('Maqueta desconocida: $m');
      return;
    }

    final m = maqueta?.toLowerCase() ?? '';
    final payload = <String, dynamic>{
      'comando': comandoOrAccion.toString(),
      'maqueta': m,
      if (target != null) 'target': target,
      if (target != null) 'piezas': target,
    };

    if (m == 'robot' || m == 'prensado' || m == 'placa1') {
      placa1.send(payload);
      return;
    }

    if (m == 'neumatico' || m == 'maquinados' || m == 'placa2') {
      placa2.send(payload);
      return;
    }

    debugPrint('Maqueta desconocida: $m');
  }

  void controlarActuador(String maqueta, dynamic actuador, [dynamic valor = true]) {
    enviarControlManual({
      'comando': 'actuador',
      'maqueta': maqueta,
      'actuador': actuador,
      'valor': valor,
      'estado': valor,
    });
  }

  void enviarControlManual(Map<String, dynamic> comando) {
    final maqueta = comando['maqueta']?.toString().toLowerCase();

    if (maqueta == 'robot' || maqueta == 'prensado') {
      placa1.send(comando);
      return;
    }

    if (maqueta == 'neumatico' || maqueta == 'maquinados') {
      placa2.send(comando);
      return;
    }

    debugPrint('Control manual rechazado: $maqueta');
  }

  Future<Map<String, dynamic>?> enviarYEsperar(
      Map<String, dynamic> comando, {
        Duration timeout = const Duration(seconds: 10),
      }) {
    final maqueta = comando['maqueta']?.toString().toLowerCase();

    if (maqueta == 'robot' ||
        maqueta == 'prensado' ||
        maqueta == 'placa1') {
      return placa1.sendAndWait(comando, timeout: timeout);
    }

    if (maqueta == 'neumatico' ||
        maqueta == 'maquinados' ||
        maqueta == 'placa2') {
      return placa2.sendAndWait(comando, timeout: timeout);
    }

    return Future.value(null);
  }

  void paroEmergencia() {
    placa1.send({
      'comando': 'emergency_stop',
    });

    placa2.send({
      'comando': 'emergency_stop',
    });
  }

  void stopEmergencia() {
    paroEmergencia();
  }

  void reset() {
    placa1.send({
      'comando': 'reset',
    });

    placa2.send({
      'comando': 'reset',
    });
  }

  void restablecerSistema() {
    reset();
  }

  void _notify() {
    notifyListeners();
  }

  @override
  void dispose() {
    placa1.removeListener(_notify);
    placa2.removeListener(_notify);

    placa1.dispose();
    placa2.dispose();

    super.dispose();
  }
}
