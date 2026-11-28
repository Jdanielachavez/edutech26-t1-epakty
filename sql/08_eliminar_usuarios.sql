-- Permite que el portal elimine cuentas de acceso (Configuración · Usuarios).
-- Solo afecta a la tabla de usuarios; la regla institution_scope sigue limitando el borrado al propio colegio.
GRANT DELETE ON paktai_edu.app_users TO paktai_service;
