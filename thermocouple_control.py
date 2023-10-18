#
# Copyright (C) 2019 Pico Technology Ltd. See LICENSE file for terms.
#
# TC-08 SINGLE MODE EXAMPLE  


import ctypes
import numpy as np
from picosdk.usbtc08 import usbtc08 as tc08
from picosdk.functions import assert_pico2000_ok

def start_thermocouples():
    # Create chandle1 and status ready for use
    chandle1 = ctypes.c_int16()
    status = {}

    # open unit
    status["open_unit"] = tc08.usb_tc08_open_unit()
    assert_pico2000_ok(status["open_unit"])
    chandle1 = status["open_unit"]

    # set mains rejection to 50 Hz
    status["set_mains"] = tc08.usb_tc08_set_mains(chandle1,0)
    assert_pico2000_ok(status["set_mains"])

    # set up channel
    # therocouples types and int8 equivalent
    # B=66 , E=69 , J=74 , K=75 , N=78 , R=82 , S=83 , T=84 , ' '=32 , X=88 
    typeT = ctypes.c_int8(84)
    status["set_channel"] = tc08.usb_tc08_set_channel(chandle1, 1, typeT)
    assert_pico2000_ok(status["set_channel"])
    status["set_channel"] = tc08.usb_tc08_set_channel(chandle1, 2, typeT)
    assert_pico2000_ok(status["set_channel"])
    status["set_channel"] = tc08.usb_tc08_set_channel(chandle1, 3, typeT)
    assert_pico2000_ok(status["set_channel"])
    status["set_channel"] = tc08.usb_tc08_set_channel(chandle1, 5, typeT)
    assert_pico2000_ok(status["set_channel"])
    status["set_channel"] = tc08.usb_tc08_set_channel(chandle1, 8, typeT)
    assert_pico2000_ok(status["set_channel"])

    # get minimum sampling interval in ms
    status["get_minimum_interval_ms"] = tc08.usb_tc08_get_minimum_interval_ms(chandle1)
    assert_pico2000_ok(status["get_minimum_interval_ms"])
     
    return chandle1




def read_thermocouples(chandle1):
    status = {}
    # get single temperature reading
    temp1 = (ctypes.c_float * 9)()
    overflow = ctypes.c_int16(0)
    units = tc08.USBTC08_UNITS["USBTC08_UNITS_CENTIGRADE"]
    status["get_single"] = tc08.usb_tc08_get_single(chandle1,ctypes.byref(temp1), ctypes.byref(overflow), units)
    assert_pico2000_ok(status["get_single"])

    # print data
    #print("Cold Junction ", temp1[0]," Ch1 ", temp1[1], " Ch2 ", temp1[2], " Ch3 ", temp1[3], " Ch5 ", temp1[5], " Ch8 ", temp1[8])
    return temp1[1], temp1[2], temp1[3], temp1[5], temp1[8]


# close unit
def stop_thermocouples(chandle):
    status = {}
    status["close_unit"] = tc08.usb_tc08_close_unit(chandle)
    assert_pico2000_ok(status["close_unit"])
    print("Thermocouple DAQ board stopped")

# display status returns
#print(status)


#therm = start_thermocouples()
#import time
#count = 0
#while count < 10:
#    therm_in = read_thermocouples(therm)
#    print(therm_in[4])
#    time.sleep(1)
#    count = count+1
    
#stop_thermocouples(therm)


