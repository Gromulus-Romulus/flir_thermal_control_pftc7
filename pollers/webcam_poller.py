#! /usr/bin/python
# Written by Dan Mandle http://dan.mandle.me September 2012
# License: GPL 2.0
 
#import os
import cv2
#from time import *
import time
import threading
import PySpin
import struct
import socket
 
camera_visible = None #seting the global variable
 
#os.system('clear') #clear the terminal (optional)

# nodemap argument comes from Spinnaker
 
class WebcamPoller(threading.Thread):
    def __init__(self, nodemap):
        threading.Thread.__init__(self)
        global camera_visible #bring it in scope
        
        # Grab device features
        features = PySpin.CCategoryPtr(nodemap.GetNode("DeviceInformation")).GetFeatures()
        ip_hex = " "

        # Find the IP address 
        for feat in features:
            node_feature = PySpin.CValuePtr(feat)
            if (PySpin.IsReadable(node_feature)):
                #print(node_feature.GetName())
                if node_feature.GetName() == "GevDeviceIPAddress":
                    ip_hex = node_feature.ToString()

        # Convert IP address represented as hexadecimal string to decimal integer
        ip_dec = int(ip_hex,0)

        # Convert IP address represented as decimal integer to string in the normal format
        ip_string = socket.inet_ntoa(struct.pack('!L', ip_dec))

        print("rtsp://"+ip_string+"/mpeg4?source=1")        

        camera_visible = cv2.VideoCapture("rtsp://"+ip_string+"/mpeg4?source=1")
        
        # What does this do? Do we want to do this??????
        #camera_visible.set(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT,720)
        #camera_visible.set(cv2.cv.CV_CAP_PROP_FRAME_WIDTH,1280)

        #retch, frame = camera_visible.read()
        #cv2.imwrite("framton.png",frame)

        self.current_value = None
        self.running = True #setting the thread running to true
        self.daemon = True

        self.im = None
        self.ret = 0
 
    def run(self):
        global camera_visible
        while self.running:
            (ret, im) = camera_visible.read()
            self.im = im
            self.ret = ret

# OKAY it works
#system = PySpin.System.GetInstance()
#cam_list = system.GetCameras()
#cam = cam_list.GetByIndex(0)
#cam.Init()
#nodemap1 = cam.GetTLDeviceNodeMap()
#wcp = WebcamPoller(nodemap1)
#wcp.daemon = True
#wcp.start() # start it up
#file_print("Visible camera setup complete")
#time.sleep(1)

#for i in range(10):
#    image_visible = wcp.im.copy()
#    cv2.imwrite("visible"+str(i)+".png",image_visible)
#    time.sleep(0.5)
