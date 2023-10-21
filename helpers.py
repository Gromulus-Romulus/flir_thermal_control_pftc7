## Helper function definitions
#  All function definitions are in one part of the script.
#  Script code immediately follows function definitions.
#

def file_print(message):
    print(message)
    logfile.write("%s\n" % message)

def closefile():
    file_print("Closing log file")
    logfile.close()
    print("Log file closed")
   
def get_devices() -> list:
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
            print(f">> WARNING: device at I2C address {i}\\ 
                  has not been identified as an EZO device, and will not be queried") 
            continue

        device_list.append(AtlasI2C(address = i, moduletype = moduletype, name = response))
    return device_list

def get_rh_temp(dev) -> tuple:
    return_string = dev.query("R").replace("\x00", "")
    return_string_2 = return_string.split(" : ")
    return_string_3 = return_string_2[1].split(",")

    rh = float(return_string_3[0])
    temp = float(return_string_3[1])
    
    return rh, temp

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
