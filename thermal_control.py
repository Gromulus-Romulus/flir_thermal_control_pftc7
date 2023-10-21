#!/usr/bin/env python

# Modification of Ben Blonder's thermal acquisition software to work with
# FLIR A700 and rewritten with Spinnaker SDK. Interface w/ Raspberry Pi 4.
#
# Updated again to run the Atlas EZO-HUM embedded humidity sensor
#
# 5 June 2023, Josef Garen
# 20 Oct 2023, Nathan Malamud
#

import time
import os
import datetime
import csv
import atexit
import save_queue

# Helper functions
from helpers import *

## NO ARAVIS - we are replacing this entirely with Spinnaker
#gi.require_version('Aravis', '0.4')
#from gi.repository import Aravis
# Aravis was the original interface for odroid
# Spinnaker is our interface for the thermal camera
# via the raspberry pi.
import PySpin

## Thermocouple controller - Pico.
# Links Rpi w/ soil, humidity, PAR sensors.
# Also links to reference plate.
import thermocouple_control_pftc as tc

## Humidity sensor
from AtlasI2C import (
     AtlasI2C
)

## Pollers disabled (FOR NOW)
# We may want the weather poller at another date
#from pollers import gps_poller, weather_poller, webcam_poller
# TODO: poller folder

ppfd_calib = 239.34

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## Set device settings

# Retrieve list of cameras from the system
cam_list = system.GetCameras()
num_cameras = cam_list.GetSize()

if num_cameras == 0:
    file_print("No camera found; program exiting.")
    exit()
elif num_cameras > 1:
    file_print("Please connect only one camera; program exiting.")
    exit()

camera = cam_list.GetByIndex(0)
nodemap_tldevice = camera.GetTLDeviceNodeMap()

camera.Init()
nodemap = camera.GetNodeMap()

file_print("Initializing image capture settings")
print_device_info(nodemap_tldevice)

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
## Establish result directory for output.
# Important to note that code should be run directlty off of the USB drive.
print ("Finding results directory")

output_dir = os.path.expanduser(
    f"/media/ubuntu/FLIRCAM/pftc7_thermal_data/results_\\
        {datetime.datetime.now().strftime('%y%m%d-%H%M%S')}"
    )

if not os.path.isdir(output_dir):
    print ("Creating results directory %s" % output_dir)
    os.makedirs(output_dir)

else:
    print ("Found results directory")

logfilename = "%s/log.txt" % output_dir
logfile = open(logfilename, "a")

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
## Weather Board Initialization

file_print("Opening log file")
os.chown(logfilename, uid, gid)
atexit.register(closefile)

file_print("Starting weather board")

try:
    device_list = get_devices()
    rh_sensor = device_list[0]
    file_print("Weather board initialized")
except:
    file_print("No weather board found; program exiting")
    exit()
    
get_rh_temp(rh_sensor)

file_print("Starting thermocouple DAQ board")
therm = tc.start_thermocouples()
atexit.register(tc.stop_thermocouples,therm)

file_print ("Finding infrared camera")
system = PySpin.System.GetInstance()

# Get current library version
version = system.GetLibraryVersion()
file_print('Library version: %d.%d.%d.%d' %
           (version.major, version.minor, version.type, version.build))

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
## Main loop
#
file_print( "Entering main loop")
counter = 0
time_start = time.time()

# Stats dictionary will hold all recorded variables
# through loop iterations. Data held in the dictionary
# will be written as csv data.
stats = {}

program_running = True
program_paused = False
program_throttled = True

# Grab nodes used later to perform autofocus and non-uniformity corrections
nuc_node = PySpin.CCommandPtr(nodemap.GetNode("NUCAction"))
auto_focus_node = PySpin.CCommandPtr(nodemap.GetNode("AutoFocus"))

# set NUCMode = "Off" (enum); set AutoFocusMethod = "Fine" (enum)
node_NUCMode = PySpin.CEnumerationPtr(nodemap.GetNode('NUCMode'))
node_NUCMode_Off = node_NUCMode.GetEntryByName("Off")
node_NUCMode.SetIntValue(node_NUCMode_Off.GetValue())

node_AutoFocusMethod = PySpin.CEnumerationPtr(nodemap.GetNode('AutoFocusMethod'))
node_AutoFocusMethod_Fine = node_AutoFocusMethod.GetEntryByName("Fine")
node_AutoFocusMethod.SetIntValue(node_AutoFocusMethod_Fine.GetValue())

# TODO: It might be nice to have a section where you can specify how you want acquisition to
# occur - e.g. continuous until an exit code is pressed, or for a fixed time or a fixed
# number of frames. It would also be nice to specify somewhere the desired framerate.
# Nathan: ideally, this could be done at the beginning of the file or with a pi.config file.

# TODO: Time is recorded using sleep statements.
# Number of images
# 25 hours -> number of seconds in 25 hours
# Take an image every 5 seconds
IMAGE_PER_SECOND = 25*60*60/5

while counter < (IMAGE_PER_SECOND):

    if program_throttled==True:
        time.sleep(5)     # Sleep time of 5 seconds           

    else:   
        if counter % 12 == 0:
            fps = counter / (time.time() - time_start)
            file_print("**** FPS = %.3f" % fps)

            freedisk_gb = float(disk_free_bytes()) / 1024 / 1024 / 1024
            file_print("**** Free: %.2f GB" % freedisk_gb)

            if freedisk_gb < 0.5:
                file_print("Exiting, disk full")
                exit()

        if counter % 24 == 0:
            file_print('Non-uniformity correction')
            nuc_node.Execute()
            time.sleep(2)

        if counter % 24 == 0:
            file_print('Autofocus')
            auto_focus_node.Execute()
            time.sleep(3)
            distance = PySpin.CFloatPtr(nodemap.GetNode('FocusDistance')).GetValue()
            PySpin.CFloatPtr(nodemap.GetNode('ObjectDistance')).SetValue(distance)
            file_print("Setting object distance to %f meters" % distance)

        # get weather stats     
        LOG_FREQ = 1
        if counter % LOG_FREQ == 0:
            file_print("Measuring ambient temperature and humidity")

            try:
                wx_rh, wx_temp = get_rh_temp(rh_sensor)
                stats['wx_temp_air_c'] = wx_temp
                stats['wx_rel_hum'] = wx_rh/100.0
            except:
                stats['wx_temp_air_c'] = -999
                stats['wx_rel_hum'] = -999
                file_print("Error reading RH and T")
            
            [   tc_soil1_c,
                tc_soil2_c,
                tc_soil3_c,
                tc_amb_c,
                ppfd_mV,
                tc_black_c
             ] = tc.read_thermocouples(therm)

            #stats['tc_soil1_c'] = tc_soil1_c
            #stats['tc_soil2_c'] = tc_soil2_c
            #stats['tc_soil3_c'] = tc_soil3_c
            stats['tc_amb_c'] = tc_amb_c
            stats['tc_black_c'] = tc_black_c
            stats['ppfd_mV_raw'] = ppfd_mV
            stats['ppfd_umol_m2_s'] = ppfd_mV*ppfd_calib

        # get current date
        stats['Date'] = datetime.datetime.now().strftime('%y%m%d-%H%M%S')

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
                
        # get camera stats every twelth iteration
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

        image_result = camera.GetNextImage(1000)

        if image_result.IsIncomplete():
            print('Image incomplete with image status %d ...' % image_result.GetImageStatus())

        else:
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

            file_print("Sending data to queue")
            save_queue.save_queue.put( (data_infrared, image_visible, fileprefix))#, uid, gid) )

            # Write data from global stats dictionary
            writer = csv.writer(open(fileprefix + '-stats.csv', 'w'), delimiter=',')
            writer.writerow(stats.keys())
            writer.writerow(stats.values())

            file_print("Summarizing data")
            stat_mean = float(data_infrared.mean()) / 100.0 - 273.15 # Temp conversion 
            file_print("Mean value = %.3f" % stat_mean)

            #stream.push_buffer(buffer)
            image_result.Release()

        counter += 1

# Deinitialize and release all cameras
# TODO: run garbage collection checking
# make sure all object references are cleaned up.
#
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
