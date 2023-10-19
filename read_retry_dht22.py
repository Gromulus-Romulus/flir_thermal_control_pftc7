import time
import board
import adafruit_dht

def read_retry(sensor):
    read_status = False
    rh = 0
    temp = 0
    tries = 0
    while not read_status:

        for i in range(10):
            try:
                rh = sensor.humidity
                temp = sensor.temperature
                time.sleep(0.01)
            except:
                a=0

        try:
            rh = sensor.humidity
            temp = sensor.temperature
            read_status = True
        except:
            read_status = False
            time.sleep(0.01)
            dur = tries+1

        if rh == None or temp == None:
            read_status = False
            time.sleep(0.01)
            dur = tries+0.1

    return rh,temp,tries
