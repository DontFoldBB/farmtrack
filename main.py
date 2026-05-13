import threading
import time
import webview
from app import app, init_telegram_monitor

PORT = 5632


def start_flask():
    app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)


def main():
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    time.sleep(0.8)  # wait for Flask to start
    init_telegram_monitor()

    webview.create_window(
        title='FarmTrack',
        url=f'http://127.0.0.1:{PORT}/profiles',
        width=1280,
        height=800,
        min_size=(960, 600),
        resizable=True,
    )
    webview.start()


if __name__ == '__main__':
    main()
