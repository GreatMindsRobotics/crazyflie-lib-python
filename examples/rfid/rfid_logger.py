from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.utils.moving_average import MovingAverage

class RFIDLogger:
    def __init__(self, cf: Crazyflie, update_period_ms=50, moving_average_length=5):
        self._cf = cf
        self._cf.connected.add_callback(self._connected)
        # The background reading of the sensor is near 200
        self._moving_average = MovingAverage(moving_average_length, fill=200)
        self._lg_rfid = LogConfig(name='RFID', period_in_ms=update_period_ms)
        self._lg_rfid.add_variable('rfid.value', 'uint16_t')

    def _connected(self, link_uri):
        try:
            self._cf.log.add_config(self._lg_rfid)
            self._lg_rfid.data_received_cb.add_callback(self._rfid_log_data)
            self._lg_rfid.error_cb.add_callback(self._rfid_log_error)

            self._lg_rfid.start()
        except KeyError as e:
            print('Could not start log configuration,'
                  '{} not found in TOC'.format(str(e)))
        except AttributeError:
            print('Could not add RFID log config, bad configuration.')

    def _rfid_log_data(self, timestamp, data, logconf):
        if("rfid.value" in data):
            self.recent_value = data["rfid.value"]
            self._moving_average.update(self.recent_value)

    def _rfid_log_error(self, logconf, msg):
        print('Error when logging %s: %s' % (logconf.name, msg))

    def get_reading(self):
        return self._moving_average.getAverage()