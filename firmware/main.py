# picowallet firmware. Step 0: WiFi console + heartbeat LED.
import time
from machine import Pin
import net

wlan = net.start()
led = Pin("LED", Pin.OUT)
while True:
    if wlan.isconnected():
        led.off(); time.sleep_ms(80); led.on(); time.sleep(2)
    else:
        led.toggle(); time.sleep(1)
