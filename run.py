import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from joinbridge_bot.app import main

# Ek simple dummy server jo Render ke port scan ko satisfy karega
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is active and running!")

def keep_alive():
    # Render automatically PORT environment variable deta hai
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    print(f"Dummy web server started on port {port} to satisfy Render...")
    server.serve_forever()

if __name__ == "__main__":
    # 1. Dummy server ko ek alag background thread mein start karte hain
    server_thread = threading.Thread(target=keep_alive)
    server_thread.daemon = True
    server_thread.start()

    # 2. Main thread mein aapka Telegram bot start karte hain
    main()
