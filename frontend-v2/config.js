// Configuración pública. Sin secretos.
// En producción (Vercel), apiUrl usa el mismo dominio. En local, apunta al backend en 8000.
window.EPAKTI_CONFIG = {
  "apiUrl": location.hostname === 'localhost' || location.hostname === '127.0.0.1'
    ? "http://localhost:8000"
    : location.origin,
  "contactEmail": "paktai_ec@outlook.com",
  "whatsappNumber": "593962719099"
};
