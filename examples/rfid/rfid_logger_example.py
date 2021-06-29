import time
from cflib.crazyflie import Crazyflie
import cflib.crtp  # noqa
from rfid_logger import RFIDLogger
from cflib.utils import uri_helper

uri = uri_helper.uri_from_env(default='radio://0/80/2M/E7E7E7E7E7')

class LoggingExample:
    def __init__(self, link_uri, moving_average_length=5):
        self._cf = Crazyflie(rw_cache='./cache')
        self._rfid_log = RFIDLogger(self._cf)

        print('Connecting to %s' % link_uri)

        # Try to connect to the Crazyflie
        self._cf.open_link(link_uri)
        # Variable used to keep main loop occupied until disconnect
        self.is_connected = True

    def _connected(self, link_uri):
        # The RFIDLogger class does the actual work of registering log callbacks
        print('Connected to %s' % link_uri, flush=True)

    def get_average_reading(self):
        return self._rfid_log.get_reading()
    
    def get_recent_value(self):
        return self._rfid_log.get_recent_value()

    def _connection_failed(self, link_uri, msg):
        """Callback when connection initial connection fails (i.e no Crazyflie
        at the specified address)"""
        print('Connection to %s failed: %s' % (link_uri, msg))
        self.is_connected = False

    def _connection_lost(self, link_uri, msg):
        """Callback when disconnected after a connection has been made (i.e
        Crazyflie moves out of range)"""
        print('Connection to %s lost: %s' % (link_uri, msg))

    def _disconnected(self, link_uri):
        """Callback when the Crazyflie is disconnected (called in all cases)"""
        print('Disconnected from %s' % link_uri)
        self.is_connected = False

if __name__ == '__main__':
    # Initialize the low-level drivers
    cflib.crtp.init_drivers()

    le = LoggingExample(uri)
    
    try:
        while le.is_connected:
            time.sleep(0.5)
            average_reading = le.get_average_reading()
            print_message = 'rfid reading: ' + str(average_reading)
            if(average_reading > 3450):
                print_message += ', very close'
            elif(average_reading > 250):
                print_message += ', above scanner'
            print(print_message, flush=True)
    except KeyboardInterrupt:
        pass