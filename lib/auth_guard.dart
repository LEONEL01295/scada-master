import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AuthGuard extends StatefulWidget {
  const AuthGuard({super.key});

  @override
  State<AuthGuard> createState() => _AuthGuardState();
}

class _AuthGuardState extends State<AuthGuard> {
  @override
  void initState() {
    super.initState();
    _checkLoginStatus();
  }

  Future<void> _checkLoginStatus() async {
    await Future.delayed(const Duration(milliseconds: 300));

    final prefs = await SharedPreferences.getInstance();
    final bool isLoggedIn = prefs.getBool('isLoggedIn') ?? false;
    final String? email = prefs.getString('userEmail');

    if (!mounted) return;

    if (!isLoggedIn || email == null || email.isEmpty) {
      Navigator.pushReplacementNamed(context, '/login');
      return;
    }

    try {
      final query = await FirebaseFirestore.instance
          .collection('usuarios')
          .where('correo', isEqualTo: email)
          .limit(1)
          .get();

      if (query.docs.isNotEmpty) {
        final userData = query.docs.first.data();
        final String rol = userData['rol']?.toString() ?? 'Alumno';
        final String estado = userData['estado']?.toString() ??
            (userData['activo'] == true ? 'Activo' : 'Pendiente');
        final bool perfilCompleto = userData['perfilCompleto'] == true;
        final bool encuestaCompletada = userData['encuestaCompletada'] == true;

        if (!mounted) return;

        if (rol == 'Pendiente' || estado == 'Pendiente' || userData['activo'] == false) {
          Navigator.pushReplacementNamed(context, '/espera');
          return;
        } else if (!perfilCompleto && rol == 'Alumno') {
          Navigator.pushReplacementNamed(context, '/formulario');
          return;
        } else if (!encuestaCompletada && rol == 'Alumno') {
          Navigator.pushReplacementNamed(context, '/encuesta');
          return;
        }
      }
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/home');
    } catch (e) {
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF0F172A),
      body: Center(
        child: CircularProgressIndicator(color: Color(0xFF38BDF8)),
      ),
    );
  }
}
