"""Proxy mínimo para el túnel temporal: publica SOLO los webhooks permitidos de n8n, nada más (ni editor ni otros flujos).

Uso:  python3 scripts/webhook_proxy.py            (escucha en 127.0.0.1:5680 y reenvía a n8n en 127.0.0.1:5678)
Luego: cloudflared tunnel --url http://127.0.0.1:5680

Reenvía el cuerpo tal cual (bytes originales) para que la firma HMAC se verifique sobre lo mismo que firmó el motor.
"""
import http.client
import http.server
import sys

# Rutas publicadas: la alerta del motor y los flujos que llama la API en producción. Nada más (ni editor ni otros flujos).
ALLOWED = {'/webhook/' + p for p in ('epakti-alerta-360', 'epakti-redactar-informe', 'epakti-examen-ocr', 'epakti-aviso-docente',
                                      'epakti-entrega-familia', 'epakti-errores', 'epakti-contacto-lead', 'paktai-alerta')}
FORWARD_HEADERS = ('content-type', 'x-epakti-signature', 'x-epakti-timestamp', 'idempotency-key', 'x-school-id', 'x-epakti-webhook-token')
MAX_BODY = 2 * 1024 * 1024
UPSTREAM = ('127.0.0.1', 5678)
LISTEN = ('127.0.0.1', int(sys.argv[1]) if len(sys.argv) > 1 else 5680)


class Proxy(http.server.BaseHTTPRequestHandler):
    server_version = 'epakty-webhook-proxy'
    sys_version = ''

    def _reply(self, status, body=b'{"detalle":"no encontrado"}'):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = self.path.split('?', 1)[0]
        if path not in ALLOWED:
            return self._reply(404)
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_BODY:
            return self._reply(413, b'{"detalle":"cuerpo demasiado grande"}')
        body = self.rfile.read(length)
        headers = {k: v for k, v in self.headers.items() if k.lower() in FORWARD_HEADERS}
        try:
            conn = http.client.HTTPConnection(*UPSTREAM, timeout=60)
            conn.request('POST', path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            self.send_header('Content-Type', resp.getheader('Content-Type', 'application/json'))
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            self._reply(502, b'{"detalle":"n8n no disponible"}')

    def do_GET(self):
        self._reply(404)

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_GET

    def log_message(self, fmt, *args):   # solo método, ruta y código; nunca cabeceras ni cuerpo
        sys.stderr.write('%s %s\n' % (self.command, args[1] if len(args) > 1 else ''))


if __name__ == '__main__':
    print(f'Proxy de webhooks en http://{LISTEN[0]}:{LISTEN[1]} -> n8n {UPSTREAM[0]}:{UPSTREAM[1]} · rutas: {", ".join(sorted(ALLOWED))}', flush=True)
    http.server.ThreadingHTTPServer(LISTEN, Proxy).serve_forever()
