There are a couple of steps necessary to get the RFID deck set up on your drone.
The RFID deck only needs its one-wire memory written once ever, you only have to write to it if you're the first person to use the deck.
If so, you need to write the deck's memory which also necessitates modifying the firmware beforehand.
The second step, which needs to happen once per drone is flashing the firmware with the RFID driver onto the drone.
Please read the procedure to flash firmware to the drone before starting either of these steps.

For safety in flashing firmware to the drone, it is highly recommended to add a URI specifier in tools/make/config.mk:
```CLOAD_CMDS += -w radio://0/80/2M/E7E7E7E7E7```
Obviously, replace the default address above with your drone's.
This ensures that when running cload, only the intended drone is flashed and not someone else's, which is very important in a classroom setting.

# Flashing firmware to the drone
If you have modified the Makefile or config.mk or just want to be sure, you should run `make clean` in the terminal.
If you've only modified the firmware code itself, you can save time without `make clean`.
Then connect the CrazyRadio dongle, turn on your drone normally and run `make cload`.
Once connected to the drone, cload will set the drone to bootloader mode and flash the firmware.
Flashing is a pretty slow process, but if you think it's abnormally so, try restarting your machine (without interrupting the flash, though)

The drone may enter recovery mode if a firmware flash is interupted, meaning it is unable to turn on normally and is stuck with solid blue LEDs.
Try to hold the power button for a few seconds, which should turn the drone on in bootloader mode.
If the LEDs are still solid blue, then you have to hold the power button down while connecting the battery to get into bootloader mode. 
Once in bootloader mode, the drone is recoverable by [flashing the firmware](https://www.bitcraze.io/documentation/repository/crazyflie-clients-python/master/userguides/recovery-mode/) through cfclient.
Keep in mind the recovery flash is not specific to a drone (it can't differentiate between drones in bootloader mode),
so make sure nobody else is recovering or flashing at the same time.

# Writing to RFID deck one-wire memory
This is necessary so that the crazyflie loads the correct driver when the RFID deck is attached.
The RFID deck is modified from a buzzer deck (but the one-wire memory doesn't know it)
and the buzzer deck sends output signals on startup through the same pins that the RFID deck takes input on. Therefore, there is an (untested) possibility for the RFID deck to be damaged if it is identified as a buzzer.
Therefore, you should disable the buzzer driver on the drone before ever installing the RFID deck; comment out `PROJ_OBJ += buzzdeck.o` in the Makefile.
Because of [a quirk](https://github.com/bitcraze/crazyflie-clients-python/issues/166) in the production firmware handling one-wire and bluetooth, you also have to build and flash with the bluetooth feature disabled. `make clean` because the Makefile was modified, `make BLE=0`, `make BLE=0 cload`

Now that the firmware is set up, install the RFID deck and only the RFID deck because the write program changes the first deck it finds.
Finally, you can run `write_deck_onewire.py` to change the RFID deck's one-wire memory.

In summary, comment out buzzdeck.o in the Makefile; clean, compile and flash with the option BLE=0; and run write-deck-onewire.py.

# Flashing the RFID driver
If you previously flashed on the rfid-deck branch to write the one-wire memory, these steps should already be completed.

If not, add the following to the Makefile in the crazyflie-firmware project so that the RFID driver is part of the firmware:
`PROJ_OBJ += rfid.o`
If you'd like, you can also re-enable the buzzdeck driver and build with bluetooth enabled. Remember to `make clean` if you do.

To check that the one-wire memory was written and the RFID driver installed correctly, connect to the drone on cfclient and open the Console window to see if the deck was recognized and the driver was initialized.
