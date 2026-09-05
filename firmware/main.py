# picowallet firmware, step 0: prove the board is alive.
# Blinks the onboard LED forever. Replace with the real app later.
from machine import Pin
import time

led = Pin("LED", Pin.OUT)
while True:
    led.toggle()
    time.sleep(0.5)
