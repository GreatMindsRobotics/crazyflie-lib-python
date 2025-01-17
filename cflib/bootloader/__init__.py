#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
#
#  Crazyflie Nano Quadcopter Client
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.
"""
Bootloading utilities for the Crazyflie.
"""
import json
import logging
import sys
import time
import zipfile
from collections import namedtuple
from typing import Callable
from typing import List
from typing import NoReturn
from typing import Optional
from typing import Tuple

from .boottypes import BootVersion
from .boottypes import TargetTypes
from .cloader import Cloader
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.mem import deck_memory
from cflib.crazyflie.mem import MemoryElement
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

logger = logging.getLogger(__name__)

__author__ = 'Bitcraze AB'
__all__ = ['Bootloader']

Target = namedtuple('Target', ['platform', 'target', 'type'])
FlashArtifact = namedtuple('FlashArtifact', ['content', 'target'])


class Bootloader:
    """Bootloader utility for the Crazyflie"""

    def __init__(self, clink=None):
        """Init the communication class by starting to communicate with the
        link given. clink is the link address used after resetting to the
        bootloader.

        The device is actually considered in firmware mode.
        """
        self.clink = clink
        self.in_loader = False

        self.page_size = 0
        self.buffer_pages = 0
        self.flash_pages = 0
        self.start_page = 0
        self.cpuid = 'N/A'
        self.error_code = 0
        self.protocol_version = 0

        self.warm_booted = False

        # Outgoing callbacks for progress and flash termination
        self.progress_cb = None  # type: Optional[Callable[[str, int], None]]
        self.error_cb = None  # type: Optional[Callable[[str], None]]
        self.terminate_flashing_cb = None  # type: Optional[Callable[[], bool]]

        self._boot_plat = None

        self._cload = Cloader(clink,
                              info_cb=None,
                              in_boot_cb=None)

    def start_bootloader(self, warm_boot=False, cf=None):
        self.warm_booted = warm_boot

        if warm_boot:
            if cf is not None and cf.link:
                cf.close_link()
            self._cload.open_bootloader_uri(self.clink)
            started = self._cload.reset_to_bootloader(TargetTypes.NRF51)
            if started:
                started = self._cload.check_link_and_get_info()
        else:
            if not self._cload.link:
                uri = self._cload.scan_for_bootloader()

                # Workaround for libusb on Windows (open/close too fast)
                time.sleep(1)

                if uri:
                    self._cload.open_bootloader_uri(uri)
                    started = self._cload.check_link_and_get_info()
                else:
                    started = False
            else:
                started = True
        if started:
            self.protocol_version = self._cload.protocol_version

            if (self.protocol_version == BootVersion.CF1_PROTO_VER_0 or
                    self.protocol_version == BootVersion.CF1_PROTO_VER_1):
                # Nothing more to do
                pass
            elif self.protocol_version == BootVersion.CF2_PROTO_VER:
                self._cload.request_info_update(TargetTypes.NRF51)
            else:
                print('Bootloader protocol 0x{:X} not '
                      'supported!'.format(self.protocol_version))

        return started

    def get_target(self, target_id):
        return self._cload.request_info_update(target_id)

    def flash(self, filename: str, targets: List[Target], cf=None):
        # Separate flash targets from decks
        platform = self._get_platform_id()
        flash_targets = [t for t in targets if t.platform == platform]
        deck_targets = [t for t in targets if t.platform == 'deck']

        # Fetch artifacts from source file
        artifacts = self._get_flash_artifacts_from_zip(filename)
        if len(artifacts) == 0:
            if len(targets) == 1:
                content = open(filename, 'br').read()
                artifacts = [FlashArtifact(content, targets[0])]
            else:
                raise(Exception('Cannot flash a .bin to more than one target!'))

        # Separate artifacts for flash and decks
        flash_artifacts = [a for a in artifacts if a.target.platform == platform]
        deck_artifacts = [a for a in artifacts if a.target.platform == 'deck']

        # Flash the MCU flash
        if len(targets) == 0 or len(flash_targets) > 0:
            self._flash_flash(flash_artifacts, flash_targets)

        # Flash the decks
        deck_update_msg = 'Deck update skipped.'
        if len(targets) == 0 or len(deck_targets) > 0:
            # only in warm boot
            if self.warm_booted:
                if self.progress_cb:
                    self.progress_cb('Restarting firmware to update decks.', int(0))

                # Reset to firmware mode
                self.reset_to_firmware()
                self.close()
                time.sleep(3)

                self._flash_deck(deck_artifacts, deck_targets)

                if self.progress_cb:
                    self.progress_cb('Deck updated! Restarting firmware.', int(100))

                # Put the crazyflie back in Bootloader mode to exit the function in the same state we entered it
                self.start_bootloader(warm_boot=True, cf=cf)

                deck_update_msg = 'Deck update complete.'
            else:
                print('Skipping updating deck on coldboot')
                deck_update_msg = 'Deck update skipped in ColdBoot mode.'

        if self.progress_cb:
            self.progress_cb(
                f'({len(flash_artifacts)}/{len(flash_artifacts)}) Flashing done! {deck_update_msg}',
                int(100))
        else:
            print('')

    def flash_full(self, cf: Optional[Crazyflie] = None,
                   filename: Optional[str] = None,
                   warm: bool = True,
                   targets: Optional[Tuple[str, ...]] = None,
                   info_cb: Optional[Callable[[int, TargetTypes], NoReturn]] = None,
                   progress_cb: Optional[Callable[[str, int], NoReturn]] = None,
                   terminate_flash_cb: Optional[Callable[[], bool]] = None):
        """
        Flash .zip or bin .file to list of targets.
        Reset to firmware when done.
        """
        if progress_cb is not None:
            self.progress_cb = progress_cb
        if terminate_flash_cb is not None:
            self.terminate_flashing_cb = terminate_flash_cb

        if not self.start_bootloader(warm_boot=warm, cf=cf):
            raise Exception('Could not connect to bootloader')

        if info_cb is not None:
            connected = (self.get_target(TargetTypes.STM32),)
            if self.protocol_version == BootVersion.CF2_PROTO_VER:
                connected += (self.get_target(TargetTypes.NRF51),)
            info_cb(self.protocol_version, connected)

        if filename is not None:
            self.flash(filename, targets, cf)
            self.reset_to_firmware()

    def _get_flash_artifacts_from_zip(self, filename):
        if not zipfile.is_zipfile(filename):
            return []

        zf = zipfile.ZipFile(filename)

        manifest = zf.read('manifest.json').decode('utf8')
        manifest = json.loads(manifest)

        if manifest['version'] != 1:
            raise Exception('Wrong manifest version')

        flash_artifacts = []
        for (file, metadata) in manifest['files'].items():
            content = zf.read(file)
            target = Target(metadata['platform'], metadata['target'], metadata['type'])
            flash_artifacts.append(FlashArtifact(content, target))

        return flash_artifacts

    def _flash_flash(self, artifacts: List[FlashArtifact], targets: List[Target]):
        for (i, artifact) in enumerate(artifacts):
            self._internal_flash(artifact, i + 1, len(artifacts))

    def reset_to_firmware(self):
        if self._cload.protocol_version == BootVersion.CF2_PROTO_VER:
            self._cload.reset_to_firmware(TargetTypes.NRF51)
        else:
            self._cload.reset_to_firmware(TargetTypes.STM32)

    def close(self):
        if self._cload:
            self._cload.close()

    def _internal_flash(self, artifact: FlashArtifact, current_file_number=1, total_files=1):

        target_info = self._cload.targets[TargetTypes.from_string(artifact.target.target)]

        image = artifact.content
        t_data = target_info

        start_page = target_info.start_page

        # If used from a UI we need some extra things for reporting progress
        factor = (100.0 * t_data.page_size) / len(image)
        progress = 0

        if self.progress_cb:
            self.progress_cb(
                'Firmware ({}/{}) Starting...'.format(current_file_number, total_files),
                int(progress))
        else:
            sys.stdout.write(
                'Flashing {} of {} to {} ({}): '.format(
                    current_file_number, total_files,
                    TargetTypes.to_string(t_data.id), artifact.target.type))
            sys.stdout.flush()

        if len(image) > ((t_data.flash_pages - start_page) *
                         t_data.page_size):
            if self.progress_cb:
                self.progress_cb('Error: Not enough space to flash the image file.', int(progress))
            else:
                print('Error: Not enough space to flash the image file.')
            raise Exception('Not enough space to flash the image file')

        if not self.progress_cb:
            logger.info(('%d bytes (%d pages) ' % (
                (len(image) - 1), int(len(image) / t_data.page_size) + 1)))
            sys.stdout.write(('%d bytes (%d pages) ' % (
                (len(image) - 1), int(len(image) / t_data.page_size) + 1)))
            sys.stdout.flush()

        # For each page
        ctr = 0  # Buffer counter
        for i in range(0, int((len(image) - 1) / t_data.page_size) + 1):
            if self.terminate_flashing_cb and self.terminate_flashing_cb():
                raise Exception('Flashing terminated')

            # Load the buffer
            if ((i + 1) * t_data.page_size) > len(image):
                self._cload.upload_buffer(
                    t_data.addr, ctr, 0, image[i * t_data.page_size:])
            else:
                self._cload.upload_buffer(
                    t_data.addr, ctr, 0,
                    image[i * t_data.page_size: (i + 1) * t_data.page_size])

            ctr += 1

            if self.progress_cb:
                progress += factor
                self.progress_cb('Firmware ({}/{}) Uploading buffer to {}...'.format(
                    current_file_number,
                    total_files,
                    TargetTypes.to_string(t_data.id)),

                    int(progress))
            else:
                sys.stdout.write('.')
                sys.stdout.flush()

            # Flash when the complete buffers are full
            if ctr >= t_data.buffer_pages:
                if self.progress_cb:
                    self.progress_cb('Firmware ({}/{}) Writing buffer to {}...'.format(
                        current_file_number,
                        total_files,
                        TargetTypes.to_string(t_data.id)),

                        int(progress))
                else:
                    sys.stdout.write('%d' % ctr)
                    sys.stdout.flush()
                if not self._cload.write_flash(t_data.addr, 0,
                                               start_page + i - (ctr - 1),
                                               ctr):
                    if self.progress_cb:
                        self.progress_cb(
                            'Error during flash operation (code {})'.format(
                                self._cload.error_code),
                            int(progress))
                    else:
                        print('\nError during flash operation (code %d). '
                              'Maybe wrong radio link?' %
                              self._cload.error_code)
                    raise Exception()

                ctr = 0

        if ctr > 0:
            if self.progress_cb:
                self.progress_cb('Firmware ({}/{}) Writing buffer to {}...'.format(
                    current_file_number,
                    total_files,
                    TargetTypes.to_string(t_data.id)),
                    int(progress))
            else:
                sys.stdout.write('%d' % ctr)
                sys.stdout.flush()
            if not self._cload.write_flash(
                    t_data.addr, 0,
                    (start_page + (int((len(image) - 1) / t_data.page_size)) -
                     (ctr - 1)), ctr):
                if self.progress_cb:
                    self.progress_cb(
                        'Error during flash operation (code {})'.format(
                            self._cload.error_code),
                        int(progress))
                else:
                    print('\nError during flash operation (code %d). Maybe'
                          ' wrong radio link?' % self._cload.error_code)
                raise Exception()

    def _get_platform_id(self):
        """Get platform identifier used in the zip manifest for curr copter"""
        identifier = 'cf1'
        if (BootVersion.is_cf2(self.protocol_version)):
            identifier = 'cf2'

        return identifier

    def _flash_deck(self, artifacts: List[FlashArtifact], targets: List[Target]):
        flash_all_targets = len(targets) == 0

        if self.progress_cb:
            self.progress_cb('Detecting deck to be updated', int(25))

        with SyncCrazyflie(self.clink, cf=Crazyflie()) as scf:
            deck_mems = scf.cf.mem.get_mems(MemoryElement.TYPE_DECK_MEMORY)
            deck_mems_count = len(deck_mems)
            if deck_mems_count == 0:
                return

            mgr = deck_memory.SyncDeckMemoryManager(deck_mems[0])
            decks = mgr.query_decks()

            for (deck_index, deck) in decks.items():
                if self.terminate_flashing_cb and self.terminate_flashing_cb():
                    raise Exception('Flashing terminated')

                # Check that we want to flash this deck
                deck_target = [t for t in targets if t == Target('deck', deck.name, 'fw')]
                if (not flash_all_targets) and len(deck_target) == 0:
                    print(f'Skipping {deck.name}')
                    continue

                # Check that we have an artifact for this deck
                deck_artifacts = [a for a in artifacts if a.target == Target('deck', deck.name, 'fw')]
                if len(deck_artifacts) == 0:
                    print(f'Skipping {deck.name}, no artifact for it in the .zip')
                    continue
                deck_artifact = deck_artifacts[0]

                if self.progress_cb:
                    self.progress_cb(f'Updating deck {deck.name}', int(50))
                print(f'Handling {deck.name}')

                # Test and wait for the deck to be started
                while not deck.is_started:
                    print('Deck not yet started ...')
                    time.sleep(500)
                    deck = mgr.query_decks()[deck_index]

                # Run a brunch of sanity checks ...
                if not deck.supports_fw_upgrade:
                    print(f'Deck {deck.name} does not support firmware update, skipping!')
                    continue

                if not deck.is_fw_upgrade_required:
                    print(f'Deck {deck.name} firmware up to date, skipping')
                    continue

                if not deck.is_bootloader_active:
                    print(f'Error: Deck {deck.name} bootloader not active, skipping!')
                    continue

                # ToDo, white the correct file there ...
                result = deck.write_sync(0, deck_artifact.content)
                if result:
                    if self.progress_cb:
                        self.progress_cb(f'Deck {deck.name} updated succesfully!', int(75))
                else:
                    if self.progress_cb:
                        self.progress_cb(f'Failed to update deck {deck.name}', int(0))
                    raise Exception(f'Failed to update deck {deck.name}')
