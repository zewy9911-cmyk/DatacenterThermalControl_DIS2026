import serial, time, sys

s = serial.Serial('COM6', 115200, timeout=3)
time.sleep(0.3)
s.write(b'\x03')
time.sleep(0.8)
s.write(b'\x03')
time.sleep(0.5)

# Query display-related pins
cmd = b'import board; pins=[p for p in dir(board) if any(k in p for k in ["LCD","TFT","SCK","MOSI","MISO","SCL","SDA","BUTTON","KEY"])]; print(pins)\r\n'
s.write(cmd)
time.sleep(2)
buf = s.read(4096)

# Also check if root_group is settable from REPL
cmd2 = b'import displayio; g=displayio.Group(); print(type(board.DISPLAY)); board.DISPLAY.root_group=g; print("root_group SET OK")\r\n'
s.write(cmd2)
time.sleep(2)
buf += s.read(4096)

s.close()
print(buf.decode('utf-8', errors='replace'))

