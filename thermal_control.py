#!/usr/bin/env python

# Modification of Ben Blonder's thermal acquisition software to work with
# FLIR A700 and rewritten with Spinnaker SDK.
#
# Updated again to run the Atlas EZO-HUM embedded humidity sensor
#
# 5 June 2023, Josef Garen
# 16 Oct 2023, Nathan Malamud
#
# TODO: Go over commented sections. Delete junk?

import pwd
import sys
import time
import os
import datetime
import numpy
import cv2
import ctypes
#import gi
import csv
import subprocess
import threading
import math
import atexit
import save_queue
import PySpin
#from read_retry_dht22 import read_retry
import thermocouple_control_pftc as tc
import board
#import adafruit_dht
#import adafruit_si7021
#import device_mgmt

## NO ARAVIS - we are replacing this entirely with Spinnaker
#gi.require_version('Aravis', '0.4')
#from gi.repository import Aravis
from AtlasI2C import (
     AtlasI2C
)

## This functionality disabled (FOR NOW) - at least we might want the weather poller
#import gps_poller
#import weather_poller
import webcam_poller

#uid = pwd.getpwnam('odroid').pw_uid
#gid = pwd.getpwnam('odroid').pw_gid

ppfd_calib = 239.34

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## Establish result directory for output.
# Important to note that code should be run directlty off of the USB drive.
print ("Finding results directory")
#output_dir = os.path.expanduser("/home/ubuntu/results_%s" % datetime.datetime.now().strftime('%y%m%d-%H%M%S'))
#output_dir = os.path.expanduser("testdir")
output_dir = os.path.expanduser("/media/ubuntu/FLIRCAM/DURIN_data/results_%s" % datetime.datetime.now().strftime('%y%m%d-%H%M%S'))
#output_dir = os.path.expanduser("/home/licor_thermal_data/results_%s" % datetime.datetime.now().strftime('%y%m%d-%H%M%S'))
if not os.path.isdir(output_dir):
    print ("Creating results directory %s" % output_dir)
    os.makedirs(output_dir)
#    os.chown(output_dir, uid, gid) 
else:
    print ("Found results directory")


logfilename = "%s/log.txt" % output_dir
logfile = open(logfilename, "a")
#sys.stderr = logfile

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## Auxiliary function definitions
#  All function definitions are in one part of the script.
#  Script code immediately follows function definitions.

def file_print(message):
    print(message)
    logfile.write("%s\n" % message)


def closefile():
    file_print("Closing log file")
    logfile.close()
    print("Log file closed")

   
def get_devices():
    device = AtlasI2C()
    device_address_list = device.list_i2c_devices()
    device_list = []
    
    for i in device_address_list:
        device.set_i2c_address(i)
        response = device.query("I")
        try:
            moduletype = response.split(",")[1] 
            response = device.query("name,?").split(",")[1]
        except IndexError:
            print(">> WARNING: device at I2C address " + str(i) + 
                  " has not been identified as an EZO device, and will not be queried") 
            continue
        device_list.append(AtlasI2C(address = i, moduletype = moduletype, name = response))
    return device_list

def get_rh_temp(dev):
    #dev.write("R")
    #time.sleep(delaytime)
    return_string = dev.query("R").replace("\x00", "")
    #print(return_string)
    return_string_2 = return_string.split(" : ")
    #print(return_string_2)
    return_string_3 = return_string_2[1].split(",")
    rh = float(return_string_3[0])
    temp = float(return_string_3[1])
    #print(rh)
    #print(temp)
    
    return rh,temp

def print_device_info(nodemap):
    """
    This function prints the device information of the camera from the transport
    layer; please see NodeMapInfo example for more in-depth comments on printing
    device information from the nodemap.

    :param nodemap: Transport layer device nodemap.
    :type nodemap: INodeMap
    :returns: True if successful, False otherwise.
    :rtype: bool
    """

    file_print('*** DEVICE INFORMATION ***\n')

    try:
        result = True
        node_device_information = PySpin.CCategoryPtr(nodemap.GetNode('DeviceInformation'))

        if PySpin.IsAvailable(node_device_information) and PySpin.IsReadable(node_device_information):
            features = node_device_information.GetFeatures()
            for feature in features:
                node_feature = PySpin.CValuePtr(feature)
                file_print('%s: %s' % (node_feature.GetName(),
                                  node_feature.ToString() if PySpin.IsReadable(node_feature) else 'Node not readable'))

        else:
            file_print('Device control information not available.')

    except PySpin.SpinnakerException as ex:
        file_print('Error: %s' % ex)
        return False

    return result

def disk_free_bytes():
    stats = os.statvfs("/")
    free = stats.f_bavail * stats.f_frsize

    return free

## TODO: What is LCD? Is this necessary?
# load in the custom scripts
#import lcd
#def lcd_close_board():
#    file_print("Closing LCDs")
#    lcd.lcd_clear()
#    for index in range(0,7):
#        lcd.lcd_led_set(index, 0)
#atexit.register(lcd_close_board)
    
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## set up LCD
#file_print ("Setting up LCD")
#lcd.lcd_setup()
#lcd.lcd_update("%.2f GB free" % (float(disk_free_bytes()) / 1024 / 1024 / 1024),0)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## get GPS going 
#file_print ("Starting GPS")
#gpsp = gps_poller.GpsPoller() # create the thread
#gpsp.daemon = True
#gpsp.start() # start it up

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## Weather Board Initialization

file_print("Opening log file")
os.chown(logfilename, uid, gid)
atexit.register(closefile)

file_print ("Starting weather board")
#rh_sensor = adafruit_dht.DHT22(board.D4)
#dur = 0
#while dur < 1000:
#    try:
#rh_sensor = adafruit_si7021.SI7021(board.I2C())
try:
    device_list = get_devices()
    rh_sensor = device_list[0]
    file_print("Weather board initialized")
except:
    file_print("No weather board found; program exiting")
    exit()
    
get_rh_temp(rh_sensor)

#    except:
        #print("ugh")
#        a=0
#    dur = dur+1
    
#if('rh_sensor' in vars()):
#    file_print("Weather board initialized")
#else:
#    file_print("No weather board found; program exiting")
    #exit()
#wp = weather_poller.WxPoller() # create the thread
#wp.daemon = True
#wp.start() # start it up

file_print("Starting thermocouple DAQ board")
therm = tc.start_thermocouples()
atexit.register(tc.stop_thermocouples,therm)

#while True:
#    tc_soil1_c, tc_soil2_c, tc_soil3_c, tc_amb_c, ppfd_mV, tc_black_c = tc.read_thermocouples(therm)
#    print(ppfd_mV)
#    print(ppfd_mV*ppfd_calib/1000)

#file_print("Waiting for GPS")
#for i in range(0,20):
#    lcd.lcd_led_set(i % 7,1)
#    time.sleep(0.5)
#    lcd.lcd_led_set(i % 7,0)
#    time.sleep(0.5)

#file_print("Trying to set time from GPS")

#if gps_poller.gpsd.utc != None and gps_poller.gpsd.utc != '':
#    gpstime = gps_poller.gpsd.utc[0:4] + gps_poller.gpsd.utc[5:7] + gps_poller.gpsd.utc[8:10] + ' ' + gps_poller.gpsd.utc[11:13] + gps_poller.gpsd.utc[13:19]
#    file_print("Setting time to GPS time %s" % gpstime)
#    os.system('sudo date -u --set="%s"' % gpstime)
#    file_print("Time has been set")
#    lcd.lcd_update(gpstime, 0)
#else:
#    file_print("GPS time not available")
#    lcd.lcd_update("No GPS time", 0)


file_print ("Finding infrared camera")
system = PySpin.System.GetInstance()

# Get current library version
version = system.GetLibraryVersion()
file_print('Library version: %d.%d.%d.%d' % (version.major, version.minor, version.type, version.build))

# Retrieve list of cameras from the system
cam_list = system.GetCameras()
num_cameras = cam_list.GetSize()

if num_cameras == 0:
    file_print ("No camera found; program exiting.")
    exit ()
elif num_cameras > 1:
    file_print ("Please connect only one camera; program exiting.")
    exit()

camera = cam_list.GetByIndex(0)
nodemap_tldevice = camera.GetTLDeviceNodeMap()

camera.Init()
nodemap = camera.GetNodeMap()

file_print ("Initializing image capture settings")
print_device_info(nodemap_tldevice)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## Set device settings
#  TODO: Shouldn't this be at the top of the script?
#

# Ensure IR mode is selected
vid_src = PySpin.CEnumerationPtr(nodemap.GetNode('VideoSourceSelector'))
vid_src_visual = vid_src.GetEntryByName("IR")
vid_src.SetIntValue(vid_src_visual.GetValue())

# Set Pixel format to Mono16
node_pixel_format = PySpin.CEnumerationPtr(nodemap.GetNode('PixelFormat'))
node_pixel_format_mono16 = node_pixel_format.GetEntryByName("Mono16")
node_pixel_format.SetIntValue(node_pixel_format_mono16.GetValue())

# Set IR Pixel format to 0.01K Tlinear (IRFormat = "TemperatureLinear10mK")
node_IRFormat = PySpin.CEnumerationPtr(nodemap.GetNode('IRFormat'))
#node_IRFormat_TL10mK = node_IRFormat.GetEntryByName("Radiometric")
node_IRFormat_TL10mK = node_IRFormat.GetEntryByName("Radiometric")
node_IRFormat.SetIntValue(node_IRFormat_TL10mK.GetValue())

# Set IR frame rate to 15 Hz (IRFrameRate = "Rate15Hz")
node_IRframerate = PySpin.CEnumerationPtr(nodemap.GetNode('IRFrameRate'))
node_IRframerate_15Hz = node_IRframerate.GetEntryByName("Rate15Hz")
node_IRframerate.SetIntValue(node_IRframerate_15Hz.GetValue())

# Set OffsetX and OffsetY = 0
node_OffsetX = PySpin.CIntegerPtr(nodemap.GetNode('OffsetX'))
node_OffsetX.SetValue(0)
node_OffsetY = PySpin.CIntegerPtr(nodemap.GetNode('OffsetY'))
node_OffsetY.SetValue(0)

# Set Height = 480 and Width = 640
node_Height = PySpin.CIntegerPtr(nodemap.GetNode('Height'))
node_Height.SetValue(480)
node_Width = PySpin.CIntegerPtr(nodemap.GetNode('Width'))
node_Width.SetValue(640)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

file_print("Setting acquisition mode to continuous")
node_acquisition_mode = PySpin.CEnumerationPtr(nodemap.GetNode('AcquisitionMode'))
if not PySpin.IsAvailable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
    file_print('Unable to set acquisition mode to continuous (enum retrieval). Aborting...')
    exit()

# Retrieve entry node from enumeration node
node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
if not PySpin.IsAvailable(node_acquisition_mode_continuous) or not PySpin.IsReadable(node_acquisition_mode_continuous):
    file_print('Unable to set acquisition mode to continuous (entry retrieval). Aborting...')
    exit()

# Retrieve integer value from entry node
acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()

# Set integer value from entry node as new value of enumeration node
node_acquisition_mode.SetIntValue(acquisition_mode_continuous)

# Set buffer handling mode to "NewestOnly" - this prevents image delays
s_node_map = camera.GetTLStreamNodeMap()

handling_mode = PySpin.CEnumerationPtr(s_node_map.GetNode('StreamBufferHandlingMode'))
if not PySpin.IsAvailable(handling_mode) or not PySpin.IsWritable(handling_mode):
    file_print('Unable to set Buffer Handling mode (node retrieval). Aborting...\n')
    exit()

handling_mode_entry = PySpin.CEnumEntryPtr(handling_mode.GetCurrentEntry())
if not PySpin.IsAvailable(handling_mode_entry) or not PySpin.IsReadable(handling_mode_entry):
    file_print('Unable to set Buffer Handling mode (Entry retrieval). Aborting...\n')
    exit()

handling_mode_entry = handling_mode.GetEntryByName('NewestOnly')
handling_mode.SetIntValue(handling_mode_entry.GetValue())
file_print('Buffer Handling Mode has been set to %s' % handling_mode_entry.GetDisplayName())


file_print( "Start thermal acquisition")
camera.BeginAcquisition()

file_print ("Creating save queue")
save_queue.initialize_queue()
def queue_close():
    file_print("Waiting for last images to save")
    save_queue.save_queue.join()
    file_print("All images saved")

atexit.register(queue_close)
#atexit.register(closefile)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## Set up web cam
#
file_print("Finding visible camera")

try:
    wcp = webcam_poller.WebcamPoller(nodemap_tldevice)
    wcp.daemon = True
    wcp.start() # start it up
    time.sleep(1)
    file_print("Visible camera setup complete")
except:
    file_print("No visible camera found, exiting")
    exit()

# set all LEDs high to verify
#for index in range(0,7):
#    lcd.lcd_led_set(index,1)
#    time.sleep(0.1)
#    lcd.lcd_led_set(index,0)
#    time.sleep(0.1)

#lcd.lcd_update("All systems OK",1)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## Main loop
#
file_print( "Entering main loop")
counter = 0
time_start = time.time()
stats = {}

program_running = True
program_paused = False #True
program_throttled = True

# Grab nodes used later to perform autofocus and non-uniformity corrections
nuc_node = PySpin.CCommandPtr(nodemap.GetNode("NUCAction"))
auto_focus_node = PySpin.CCommandPtr(nodemap.GetNode("AutoFocus"))

### set NUCMode = "Off" (enum); set AutoFocusMethod = "Fine" (enum)
node_NUCMode = PySpin.CEnumerationPtr(nodemap.GetNode('NUCMode'))
node_NUCMode_Off = node_NUCMode.GetEntryByName("Off")
node_NUCMode.SetIntValue(node_NUCMode_Off.GetValue())

node_AutoFocusMethod = PySpin.CEnumerationPtr(nodemap.GetNode('AutoFocusMethod'))
node_AutoFocusMethod_Fine = node_AutoFocusMethod.GetEntryByName("Fine")
node_AutoFocusMethod.SetIntValue(node_AutoFocusMethod_Fine.GetValue())

# TODO: It might be nice to have a section where you can specify how you want acquisition to
# occur - e.g. continuous until an exit code is pressed, or for a fixed time or a fixed
# number of frames. It would also be nice to specify somewhere the desired framerate.

# TODO: What are the units for this counter?
while counter < (25*60*60/5):
#while(program_running==True): # Potential infinite loop
#    (b_left, b_right) = lcd.lcd_check_buttons(50)
#    if b_left == True:
#        program_throttled = not program_throttled
#        file_print("Left button pressed - throttle state now %d" % program_throttled)
#    if b_right == True:
#        program_paused = not program_paused
#        file_print("Right button pressed - pause state now %d" % program_paused)
#    if b_right == True and b_left == True:
#        file_print("Both buttons pressed - exiting and shutting down")
#        os.system("sudo shutdown now -h")

    if program_throttled==True:
        time.sleep(5)                
#            lcd.lcd_led_set(6,i%2)
#    else:
#        lcd.lcd_led_set(6,1)

    if program_paused==True:
#        lcd.lcd_update("Paused",0)
        time.sleep(1)
    else:   
        if counter % 12 == 0:
            fps = counter / (time.time() - time_start)
            file_print("**** FPS = %.3f" % fps)

            freedisk_gb = float(disk_free_bytes()) / 1024 / 1024 / 1024
#            lcd.lcd_update("Diskfree: %.2f GB" % freedisk_gb, 0)
            file_print("**** Free: %.2f GB" % freedisk_gb)

            if freedisk_gb < 0.5:
                file_print("Exiting, disk full")
                exit()

        if counter % 24 == 0:
            file_print('Non-uniformity correction')
#            device.execute_command("NUCAction")
            nuc_node.Execute()
            time.sleep(2)

        if counter % 24 == 0:
            file_print('Autofocus')
#            device.execute_command("AutoFocus")
            auto_focus_node.Execute()
            time.sleep(3)
            distance = PySpin.CFloatPtr(nodemap.GetNode('FocusDistance')).GetValue()
            PySpin.CFloatPtr(nodemap.GetNode('ObjectDistance')).SetValue(distance)
#            distance = device.get_float_feature_value("FocusDistance")
            file_print("Setting object distance to %f meters" % distance)
#            device.set_float_feature_value("ObjectDistance", distance)

        # get weather stats     
        #if counter % 12 == 0:
        # Previously only updated every 12th measurement
        if counter % 1 == 0:
            file_print("Measuring ambient temperature and humidity")
            #wx_rh, wx_temp, wx_tries = read_retry(rh_sensor)
            #wx_rh = rh_sensor.relative_humidity
            #wx_temp = rh_sensor.temperature
            try:
                wx_rh, wx_temp = get_rh_temp(rh_sensor)
                stats['wx_temp_air_c'] = wx_temp
                stats['wx_rel_hum'] = wx_rh/100.0
            except:
                stats['wx_temp_air_c'] = -999
                stats['wx_rel_hum'] = -999
                file_print("Error reading RH and T")
                
            
            tc_soil1_c, tc_soil2_c, tc_soil3_c, tc_amb_c, ppfd_mV, tc_black_c = tc.read_thermocouples(therm)
            #stats['tc_soil1_c'] = tc_soil1_c
            #stats['tc_soil2_c'] = tc_soil2_c
            #stats['tc_soil3_c'] = tc_soil3_c
            stats['tc_amb_c'] = tc_amb_c
            stats['tc_black_c'] = tc_black_c
            stats['ppfd_mV_raw'] = ppfd_mV
            stats['ppfd_umol_m2_s'] = ppfd_mV*ppfd_calib
#        if counter % 10 == 0:
#            (wx_status, wx_vals) = wp.wx
#            if (wx_status == True):
#                lcd.lcd_led_set(2,1)
#            else:
#                lcd.lcd_led_set(2,0)    
#            stats['wx_uv_lux'] = wx_vals[0] # 0-based indexing
#            stats['wx_vis_lux'] = wx_vals[1]
#            stats['wx_ir_lux'] = wx_vals[2]
#            stats['wx_temp_air_c'] = wx_vals[3]
#            stats['wx_rel_hum_pct'] = wx_vals[4]
#            stats['wx_pressure_hpa'] = wx_vals[5]

        # get gps stats
#        global gpsd
#        stats['gps_latitude']=gps_poller.gpsd.fix.latitude
#        stats['gps_longitude']=gps_poller.gpsd.fix.longitude
#        stats['gps_num_satellites']=len(gps_poller.gpsd.satellites)
#        stats['gps_utc']=gps_poller.gpsd.utc
#        stats['gps_time']=gps_poller.gpsd.fix.time
#        if stats['gps_num_satellites']==0:
#            lcd.lcd_led_set(1,0)
#        else:
#            lcd.lcd_led_set(1,1)
    
        # get current date
        stats['Date'] = datetime.datetime.now().strftime('%y%m%d-%H%M%S')


#        file_print("**** Lat: %.3f Lon: %.3f Numsats: %d" % (stats["gps_latitude"], stats['gps_longitude'], stats['gps_num_satellites']))


        if counter % 12 == 0:
            file_print("Adjusting camera settings based on current T and RH")
            try:
                stat_atm_temp = float(stats['wx_temp_air_c']) + 273.15
                PySpin.CFloatPtr(nodemap.GetNode('AtmosphericTemperature')).SetValue(stat_atm_temp)            
            except:
                stat_atm_temp = -999
                file_print("Temperature error")

            try:
                stat_atm_rh  = float(stats['wx_rel_hum'])
                PySpin.CFloatPtr(nodemap.GetNode('RelativeHumidity')).SetValue(stat_atm_rh)
            except:
                stat_atm_rh = -999
                file_print("RH error")
                
#            device.set_float_feature_value("AtmosphericTemperature",stat_atm_temp)
#            device.set_float_feature_value("RelativeHumidity",stat_atm_rh)



        # get camera stats
        if counter % 12 == 0:
            stats['AtmosphericTemperature'] = PySpin.CFloatPtr(nodemap.GetNode("AtmosphericTemperature")).GetValue()
            stats['EstimatedTransmission'] = PySpin.CFloatPtr(nodemap.GetNode("EstimatedTransmission")).GetValue()
            stats['ExtOpticsTemperature'] = PySpin.CFloatPtr(nodemap.GetNode("ExtOpticsTemperature")).GetValue()
            stats['ExtOpticsTransmission'] = PySpin.CFloatPtr(nodemap.GetNode("ExtOpticsTransmission")).GetValue()
            stats['ObjectDistance'] = PySpin.CFloatPtr(nodemap.GetNode("ObjectDistance")).GetValue()
            stats['ObjectEmissivity'] = PySpin.CFloatPtr(nodemap.GetNode("ObjectEmissivity")).GetValue()
            stats['ReflectedTemperature'] = PySpin.CFloatPtr(nodemap.GetNode("ReflectedTemperature")).GetValue()
            stats['RelativeHumidity'] = PySpin.CFloatPtr(nodemap.GetNode("RelativeHumidity")).GetValue()
            stats['FocusDistance'] = PySpin.CFloatPtr(nodemap.GetNode("FocusDistance")).GetValue()
            stats['TSens'] = PySpin.CFloatPtr(nodemap.GetNode("TSens")).GetValue()
            stats['alpha1'] = PySpin.CFloatPtr(nodemap.GetNode("alpha1")).GetValue()
            stats['alpha2'] = PySpin.CFloatPtr(nodemap.GetNode("alpha2")).GetValue()
            stats['B'] = PySpin.CFloatPtr(nodemap.GetNode("B")).GetValue()
            stats['beta1'] = PySpin.CFloatPtr(nodemap.GetNode("beta1")).GetValue()
            stats['beta2'] = PySpin.CFloatPtr(nodemap.GetNode("beta2")).GetValue()
            stats['F'] = PySpin.CFloatPtr(nodemap.GetNode("F")).GetValue()
            stats['J0'] = PySpin.CIntegerPtr(nodemap.GetNode("J0")).GetValue()
            stats['J1'] = PySpin.CFloatPtr(nodemap.GetNode("J1")).GetValue()
            stats['R'] = PySpin.CFloatPtr(nodemap.GetNode("R")).GetValue()
            stats['X'] = PySpin.CFloatPtr(nodemap.GetNode("X")).GetValue()






        fileprefix = '%s/out_%s_%d' % (output_dir, stats['Date'], counter)
        file_print("Setting output location %s" % fileprefix)
#        lcd.lcd_update(stats['Date'], 0)


        #buffer = stream.pop_buffer ()
        image_result = camera.GetNextImage(1000)

        #if buffer:
        if image_result.IsIncomplete():
            print('Image incomplete with image status %d ...' % image_result.GetImageStatus())

        else:
#            lcd.lcd_led_set(0,1)
            file_print('Reading infrared image data')
            data_infrared = image_result.GetNDArray()
            #img = numpy.fromstring(ctypes.string_at(buffer.data_address(), buffer.size), dtype=numpy.uint16).reshape(480,640)
            #data_infrared = numpy.ctypeslib.as_array(ctypes.cast(buffer.get_data(), ctypes.POINTER(ctypes.c_uint16)), (buffer.get_image_height(), buffer.get_image_width()))
            #data_infrared = data_infrared.copy()
            #print(data_infrared)

            file_print('Reading visible image data')
            #ret,image_visible = camera_visible.read()
            #image_visible = image_visible.copy()
            image_visible = wcp.im.copy()       

#            if wcp.ret==True:
#                lcd.lcd_led_set(3,1)
#            else:
#                lcd.lcd_led_set(3,0)

            file_print("Sending data to queue")
            save_queue.save_queue.put( (data_infrared, image_visible, fileprefix))#, uid, gid) )

#            numpy.save(fileprefix + '-infrared-data.npy', data_infrared)
#        os.chown(fileprefix + "-infrared-data.npy", uid, gid)

        # generate a PNG preview of the infrared data, coloring by temperature
#            imgscaled = ((data_infrared - numpy.percentile(data_infrared,1)).astype(float) / (numpy.percentile(data_infrared,99) - numpy.percentile(data_infrared,2.5)).astype(float)) * 255
#            imgscaled[imgscaled < 0] = 0
#            imgscaled[imgscaled > 255] = 255
#            imgscaled = cv2.convertScaleAbs(imgscaled)
#            imgscaledcolored = cv2.applyColorMap(imgscaled, cv2.COLORMAP_OCEAN)
#            cv2.imwrite(fileprefix + '-infrared.png', imgscaledcolored)
#            cv2.imwrite(fileprefix + "-visible.png",image_visible)


            writer = csv.writer(open(fileprefix + '-stats.csv', 'w'),delimiter=',')
            writer.writerow(stats.keys())
            writer.writerow(stats.values())
#            os.chown(fileprefix + "-stats.csv", uid, gid)

            file_print("Summarizing data")
            stat_mean = float(data_infrared.mean()) / 100.0 - 273.15 
            file_print("Mean value = %.3f" % stat_mean)
#            lcd.lcd_update("%d %.1f %.2f" % (counter, stat_mean, freedisk_gb),1)

            #stream.push_buffer(buffer)
            image_result.Release()
#        else:
#            lcd.lcd_led_set(0,0)
#            file_print('No buffer obtained')

        counter = counter + 1

# Deinitialize and release all cameras
camera.EndAcquisition()
camera.DeInit()
del camera
cam_list.Clear()
system.ReleaseInstance()
file_print("Stopping acquisition")
#queue_close()
#closefile()
#tc.stop_thermocouples(therm)
exit()
