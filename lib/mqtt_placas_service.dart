import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class MqttPlacasService extends ChangeNotifier {
  bool conectado = false;
  bool conectando = false;

  // Ahora esta IP será la IP LOCAL DE TU PLACA EMISOR.
  // Ejemplo común cuando la placa crea su propia red WiFi:
  // 192.168.4.1
  String broker = '192.168.4.1';

  // Se conserva port para no romper tu home.dart.
  // En HTTP normalmente se usa el puerto 80.
  int port = 80;

  Map<String, dynamic> estadoGateway = {};
  Map<String, dynamic> estadoEmisor = {};
  Map<String, dynamic> estadoReceptor = {};

  String ultimoMensaje = 'Sin conexión con la placa';

  Timer? _statusTimer;

  Uri _uri(String path, [Map<String, String>? query]) {
    return Uri.http('$broker:$port', path, query);
  }

  Future<void> conectar({
    required String brokerIp,
    int mqttPort = 80,
  }) async {
    if (conectado || conectando) return;

    broker = brokerIp.trim();
    port = mqttPort;

    conectando = true;
    ultimoMensaje = 'Conectando con placa $broker:$port...';
    notifyListeners();

    try {
      final ok = await _leerEstado();

      if (!ok) {
        conectado = false;
        conectando = false;
        ultimoMensaje =
            'No se pudo conectar. Verifica la IP de la placa y que esté en la misma red.';
        notifyListeners();
        return;
      }

      conectado = true;
      conectando = false;
      ultimoMensaje = 'Conectado a placa local $broker:$port';
      notifyListeners();

      _statusTimer?.cancel();
      _statusTimer = Timer.periodic(
        const Duration(seconds: 1),
        (_) => _leerEstado(),
      );
    } catch (e) {
      conectado = false;
      conectando = false;
      ultimoMensaje = 'Error conectando con la placa: $e';
      notifyListeners();
    }
  }

  Future<bool> _leerEstado() async {
    try {
      final response = await http
          .get(
            _uri('/status'),
          )
          .timeout(
            const Duration(seconds: 3),
          );

      if (response.statusCode != 200) {
        ultimoMensaje = 'Error HTTP ${response.statusCode}: ${response.body}';
        notifyListeners();
        return false;
      }

      final data = jsonDecode(response.body);

      if (data is Map<String, dynamic>) {
        _procesarEstado(data);
        ultimoMensaje = 'Estado recibido: ${response.body}';
        notifyListeners();
        return true;
      }

      ultimoMensaje = 'Respuesta inválida de la placa: ${response.body}';
      notifyListeners();
      return false;
    } catch (e) {
      ultimoMensaje = 'No se pudo leer /status: $e';
      notifyListeners();
      return false;
    }
  }

  void _procesarEstado(Map<String, dynamic> data) {
    /*
      La placa puede responder de dos formas:

      FORMA 1:
      {
        "gateway": {...},
        "emisor": {...},
        "receptor": {...}
      }

      FORMA 2:
      {
        "device": "emisor",
        "estado": 1,
        "running": true,
        "emergency": false,
        "mensaje": "Trabajando"
      }
    */

    if (data.containsKey('gateway')) {
      final gateway = data['gateway'];
      if (gateway is Map) {
        estadoGateway = Map<String, dynamic>.from(gateway);
      }
    }

    if (data.containsKey('emisor')) {
      final emisor = data['emisor'];
      if (emisor is Map) {
        estadoEmisor = Map<String, dynamic>.from(emisor);
      }
    }

    if (data.containsKey('receptor')) {
      final receptor = data['receptor'];
      if (receptor is Map) {
        estadoReceptor = Map<String, dynamic>.from(receptor);
      }
    }

    final device = data['device']?.toString();

    if (device == 'gateway') {
      estadoGateway = data;
    } else if (device == 'emisor') {
      estadoEmisor = data;
    } else if (device == 'receptor') {
      estadoReceptor = data;
    } else {
      estadoGateway = data;
    }
  }

  Future<void> enviarComando({
    required String destino,
    required String comando,
  }) async {
    if (!conectado) {
      ultimoMensaje = 'No se puede enviar comando: placa no conectada';
      notifyListeners();
      return;
    }

    try {
      /*
        Tu placa emisor debe tener esta ruta:

        /cmd?to=todos&cmd=start
        /cmd?to=todos&cmd=stop
        /cmd?to=todos&cmd=reset
        /cmd?to=todos&cmd=emergency_stop

        También sirve para control individual:

        /cmd?to=emisor&cmd=start
        /cmd?to=receptor&cmd=stop
      */

      final response = await http
          .get(
            _uri(
              '/cmd',
              {
                'to': destino,
                'cmd': comando,
              },
            ),
          )
          .timeout(
            const Duration(seconds: 3),
          );

      if (response.statusCode == 200) {
        ultimoMensaje =
            'Comando enviado a $destino: $comando | Respuesta: ${response.body}';

        try {
          final data = jsonDecode(response.body);
          if (data is Map<String, dynamic>) {
            _procesarEstado(data);
          }
        } catch (_) {
          // Si la placa responde texto simple, no pasa nada.
        }

        notifyListeners();

        await _leerEstado();
      } else {
        ultimoMensaje =
            'Error enviando comando. HTTP ${response.statusCode}: ${response.body}';
        notifyListeners();
      }
    } catch (e) {
      ultimoMensaje = 'Error enviando comando a la placa: $e';
      notifyListeners();
    }
  }

  void iniciarTodo() {
    enviarComando(destino: 'todos', comando: 'start');
  }

  void detenerTodo() {
    enviarComando(destino: 'todos', comando: 'stop');
  }

  void resetearTodo() {
    enviarComando(destino: 'todos', comando: 'reset');
  }

  void paroEmergencia() {
    enviarComando(destino: 'todos', comando: 'emergency_stop');
  }

  void iniciarEmisor() {
    enviarComando(destino: 'emisor', comando: 'start');
  }

  void detenerEmisor() {
    enviarComando(destino: 'emisor', comando: 'stop');
  }

  void iniciarReceptor() {
    enviarComando(destino: 'receptor', comando: 'start');
  }

  void detenerReceptor() {
    enviarComando(destino: 'receptor', comando: 'stop');
  }

  void desconectar() {
    _statusTimer?.cancel();
    _statusTimer = null;

    conectado = false;
    conectando = false;
    ultimoMensaje = 'Desconectado de la placa local';
    notifyListeners();
  }

  @override
  void dispose() {
    desconectar();
    super.dispose();
  }
}
