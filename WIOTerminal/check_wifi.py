import sys
import time

import serial


PORT = sys.argv[1] if len(sys.argv) > 1 else "COM6"
BAUD = 115200


def send_and_read(ser, command, wait_s=1.2):
	ser.write(b"\r" + command.encode("utf-8") + b"\r\n")
	time.sleep(wait_s)
	return ser.read(16384).decode("utf-8", errors="replace")


with serial.Serial(PORT, BAUD, timeout=2) as s:
	time.sleep(0.4)
	s.write(b"\r\x03\x03")  # break out of running code into the REPL
	time.sleep(1.5)
	s.reset_input_buffer()

	checks = [
		("uname", "import os; print(os.uname())", 1.0),
		("wifi settings", "import os; print({'WIFI_SSID': os.getenv('WIFI_SSID'), 'SERVER_HOST': os.getenv('SERVER_HOST'), 'SERVER_PORT': os.getenv('SERVER_PORT')})", 1.0),
		("root dir", "import os; print(os.listdir('/'))", 1.0),
		("lib dir", "import os; print(os.listdir('/lib'))", 1.0),
		("board net pins", "import board; print([n for n in dir(board) if 'RTL' in n or 'WIFI' in n or 'ESP' in n or 'NINA' in n])", 1.0),
		("import wifi", "import wifi; print('wifi OK')", 1.0),
		("import socketpool", "import socketpool; print('socketpool OK')", 1.0),
		("import adafruit_requests", "import adafruit_requests; print('adafruit_requests OK')", 1.0),
		("import adafruit_esp32spi", "from adafruit_esp32spi import adafruit_esp32spi; print('adafruit_esp32spi OK')", 1.0),
		(
			"RTL connect + HTTP probe",
			"import os,time,board,busio,digitalio,adafruit_requests; from adafruit_esp32spi import adafruit_esp32spi, adafruit_esp32spi_socketpool; ssid=os.getenv('WIFI_SSID'); pw=os.getenv('WIFI_PASSWORD'); host=os.getenv('SERVER_HOST'); port=os.getenv('SERVER_PORT','8000'); spi=busio.SPI(board.RTL_CLK, board.RTL_MOSI, board.RTL_MISO); cs=digitalio.DigitalInOut(board.RTL_CS); d=digitalio.DigitalInOut(board.RTL_DIR); d.direction=digitalio.Direction.OUTPUT; p=digitalio.DigitalInOut(board.RTL_PWR); p.direction=digitalio.Direction.OUTPUT; ready=digitalio.DigitalInOut(board.RTL_READY); ready.direction=digitalio.Direction.INPUT;\nfor mode in (True, False):\n print('\\n-- RTL_DIR =', int(mode), '--'); d.value=mode; p.value=False; time.sleep(0.5); p.value=True; trace=[]; t0=time.monotonic();\n while time.monotonic()-t0 < 1.8:\n  v=bool(ready.value);\n  if not trace or trace[-1] != v: trace.append(v);\n  time.sleep(0.05);\n print('ready_trace=', trace, 'ready_now=', bool(ready.value));\n try:\n  esp=adafruit_esp32spi.ESP_SPIcontrol(spi, cs, ready, p); print('assoc->', ssid); esp.connect_AP(ssid, pw); time.sleep(2.0); print('ip=', esp.pretty_ip(esp.ip_address)); pool=adafruit_esp32spi_socketpool.SocketPool(esp); req=adafruit_requests.Session(pool); r=req.get('http://{}:{}/api/wio'.format(host, port), timeout=5); print('http=', getattr(r,'status_code',None), r.text[:120]); r.close(); break\n except Exception as e:\n  print('FAIL', type(e).__name__, e)",
			12.0,
		),
		("modules", "help('modules')", 2.5),
	]

	for title, command, wait_s in checks:
		print("\n=== {} ===".format(title))
		sys.stdout.write(send_and_read(s, command, wait_s))
