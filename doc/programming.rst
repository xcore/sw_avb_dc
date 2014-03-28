Programming guide
+++++++++++++++++

Getting started 
===============

Obtaining the latest firmware
-----------------------------

#. Log into xmos.com and access `My XMOS` |submenu| `Reference Designs`
#. Request access to the `XMOS AVB-DC Software Release` by clicking the `Request Access` link under `AVB DAISY-CHAIN KIT`. An email will be sent to your registered email address when access is granted.
#. A `Download` link will appear where the `Request Access` link previously appeared. Click and download the firmware zip.


Installing xTIMEcomposer Tools Suite
------------------------------------

The AVB-DC software requires xTIMEcomposer version 13.0.2 or greater. It can be downloaded at the following URL
https://www.xmos.com/en/support/downloads/xtimecomposer


Importing and building the firmware
-----------------------------------

To import and build the firmware, open xTIMEcomposer Studio and
follow these steps:

#. Choose `File` |submenu| `Import`.

#. Choose `General` |submenu| `Existing Projects into Workspace` and
   click **Next**.

#. Click **Browse** next to **`Select archive file`** and select
   the firmware .zip file downloaded in section 1.

#. Make sure that all projects are ticked in the
   `Projects` list.
 
#. Click **Finish**.

#. Select the ``app_daisy_chain`` project in the Project Explorer and click the **Build** icon in the main toolbar.

Installing the application onto flash memory
--------------------------------------------

#. Connect the xTAG-2 debug adapter (XA-SK-XTAG2) to the first sliceKIT core board. 
#. Connect the xTAG-2 to the debug adapter.
#. Plug the xTAG-2 into your development system via USB.
#. Plug in the 12V power adapter and connect it to the sliceKIT core board.
#. In xTIMEcomposer, right-click on the binary within the *app_daisy_chain/bin* folder of the project.
#. Choose `Flash As` |submenu| `Flash Configurations`.
#. Double click `xCORE Application` in the left panel.
#. Choose `hardware` in `Device options` and select the relevant xTAG-2 adapter.
#. Click on **Apply** if configuration has changed.
#. Click on **Flash**. Once completed, disconnect the power from the sliceKIT core board.
#. Repeat steps 1 through 8 for the second sliceKIT.

Using the Command Line Tools
----------------------------

#. Open the XMOS command line tools (Command Prompt) and
   execute the following command:


   ::

       xrun --xscope <binary>.xe

#. If multiple xTAG-2s are connected, obtain the adapter ID integer by executing:

   :: 

      xrun -l

#. Execute the `xrun` command with the adapter ID flag

   :: 

      xrun --id <id> --xscope <binary>.xe



Installing the application onto flash via Command Line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. Connect the xTAG-2 debug adapter to the relevant development
   board, then plug the xTAG-2 into your PC or Mac.

Using Command Line Tools
------------------------


#. Open the XMOS command line tools (Command Prompt) and
   execute the following command:

   ::

       xflash <binary>.xe

#. If multiple xTAG-2s are connected, obtain the adapter ID integer by executing:

   :: 

      xrun -l

#. Execute the `xflash` command with the adapter ID flag

   :: 

      xflash --id <id> <binary>.xe

Source code structure
=====================

Directory Structure
-------------------

The source code is split into several top-level directories which are
presented as separate projects in xTIMEcomposer Studio. These are split into
modules and applications.

Applications build into a single
executable using the source code from the modules. The modules used by
an application are specified using the ``USED_MODULES`` variable in
the application Makefile. For more details on this module structure
please see the XMOS build system document *Using XMOS Makefiles (X6348)*.

The AVB-DC source package contains a simple demonstration application `app_daisy_chain`.

Core AVB modules are presented in the sc_avb repository. Some support modules originate in other repositories:

.. list-table:: 
 :header-rows: 1

 * - Directory
   - Description
   - Repository
 * - module_ethernet
   - Ethernet MAC
   - sc_ethernet
 * - module_ethernet_board_support
   - Hardware specific board configuration for Ethernet MAC
   - sc_ethernet
 * - module_ethernet_smi
   - SMI interface for reading/writing registers to the Ethernet PHY
   - sc_ethernet
 * - module_otp_board_info
   - Interface for reading serial number and MAC addresses from OTP memory
   - sc_otp
 * - module_i2c_simple
   - Two wire configuration protocol code.
   - sc_i2c
 * - module_random
   - Random number generator
   - sc_util
 * - module_logging
   - Debug print library
   - sc_util
 * - module_slicekit_support
   - sliceKIT core board support
   - sc_slicekit_support

The following modules in sc_avb contain the core AVB code and are needed by
every application:

.. list-table:: 
 :header-rows: 1

 * - Directory
   - Description
 * - module_avb
   - Main AVB code for control and configuration.
 * - module_avb_1722
   - IEEE 1722 transport (listener and talker functionality).
 * - module_avb_1722_1
   - IEEE P1722.1 AVB control protocol.
 * - module_avb_1722_maap
   - IEEE 1722 MAAP - Multicast address allocation code.
 * - module_avb_audio
   - Code for media FIFOs and audio hardware interfaces (I2S).
 * - module_avb_flash
   - Flash access for firmware upgrade
 * - module_avb_media_clock
   - Media clock server code for clock recovery.
 * - module_avb_srp
   - 802.1Qat stream reservation (SRP/MRP/MVRP) code.
 * - module_avb_util
   - General utility functions used by all modules.
 * - module_gptp
   - 802.1AS Precision Time Protocol code.
     

Key Files
---------

.. list-table::
 :header-rows: 1

 * - File
   - Description
 * - ``avb_api.h``
   - Header file containing declarations for the core AVB control API.
 * - ``avb_1722_1_app_hooks.h``
   - Header file containing declarations for hooks into 1722.1  
 * - ``ethernet_rx_client.h`` 
   - Header file for clients that require direct access to the ethernet MAC
     (RX). 
 * - ``ethernet_tx_client.h``
   - Header file for clients that require direct access to the ethernet MAC
     (TX). 
 * - ``gptp.h``
   - Header file for access to the PTP server.
 * - ``audio_i2s.h``
   - Header file containing the I2S audio component.

Entity Firmware Upgrade (EFU)
=============================

Introduction
------------

The EFU loader is a flash device firmware upgrade mechanism for AVB endpoints.

The firmware upgrade implementation for XMOS AVB devices uses a subset of the
Memory Object Upload mechanism described in Annex D of the 1722.1-2013 standard:

http://standards.ieee.org/findstds/standard/1722.1-2013.html

Supported functionality:

 * Upload of new firmware to AVB device
 * Reboot of device on firmware upgrade via the 1722.1 REBOOT command

xTIMEcomposer v13.0.2 or later is required to generate flash images compatible with
the AVB-DC flash interface.

SPI Flash IC Requirements and Configuration
-------------------------------------------

The current version of the AVB-DC EFU functionality supports boot flashes with the following 
properties only:

 * A page size of 256 bytes
 * Total flash size greater than or equal to the size required to store the boot loader, factory image and maximum sized upgrade image.

Other flash specific configuration parameters may be changed via ``avb_flash_conf.h``:

.. doxygendefine:: FLASH_SECTOR_SIZE
.. doxygendefine:: FLASH_SPI_CMD_ERASE
.. doxygendefine:: FLASH_NUM_PAGES
.. doxygendefine:: FLASH_MAX_UPGRADE_IMAGE_SIZE

Installing the factory image to the device
------------------------------------------

Once the AVB-DC application has been built:

#. Open the XMOS command line tools (Command Prompt) and
   execute the following command:

   ::

       xflash --boot-partition-size 262144 <binary>.xe

#. If multiple xTAG-2s are connected, obtain the adapter ID integer by executing:

   :: 

      xrun -l

#. Execute the `xflash` command with the adapter ID flag

   :: 

      xflash --id <id> --boot-partition-size 262144 <binary>.xe

   .. note::

      Ignore the following warning which is informative only: 

      ``Warning: F03098 Factory image and boot loader cannot be write-protected on flash device on node "0"``

This programs the factory default firmware image into the flash device. 

To use the firmware upgrade mechanism you need to build a firmware upgrade
image:

#. Edit the ``aem_entity_strings.h.in`` file and increment the ``AVB_1722_1_FIRMWARE_VERSION_STRING`` and 
   ``AVB_1722_1_ADP_MODEL_ID`` in ``avb_conf.h``.

#. Rebuild the application

To generate the firmware upgrade image run the following command:

   ::

       xflash --factory-version 13 --upgrade 1 <binary>.xe -o upgrade_image.bin

You should now have the firmware upgrade file upgrade_image.bin which can be transferred to the 
AVB end station.

Using the avdecc-lib CLI Controller to upgrade firmware
-------------------------------------------------------

..note ::
  See the XMOS document *AVB System Requirements Guide* for installation details of the ``avdecccmdline`` tool.

#. To program the new firmware, first run ``avdecccmdline`` and select the interface number that represents 
   the Ethernet interface that the AVB network is connected to:

   ::

       Enter the interface number (1-7): 1

#. Use the ``list`` command to view all AVB end stations on the network:

   ::

       $ list
       
       End Station | Name         | Entity ID          | Firmware Version | MAC
       ---------------------------------------------------------------------------------
       C         0 | AVB 4in/4out | 0x002297fffe005279 |            1.0.0 | 002297005279

#. Select the end station that you wish to upgrade using the ``select`` command with the integer ID shown in the ``End Station``
   column of the ``list`` output and two additional zeroes indicating the Entity and Configuration indices:

   ::

       $ select 0 0 0

#. Begin the firmware upgrade process using the ``upgrade`` command with the full path of the ``upgrade_image.bin``
   file:

   ::

       $ upgrade /path/to/upgrade_image.bin
       Erasing image...
       Successfully erased.
       Uploading image...
       ################################################################################
       Successfully upgraded image.
       Do you want to reboot the device? [y/n]: y

#. The device should now reboot and re-enumerate with an upgraded Firmware Version string. Test this using the ``list`` command:

   ::

       $ list
       
       End Station | Name         | Entity ID          | Firmware Version | MAC
       ---------------------------------------------------------------------------------
       C         0 | AVB 4in/4out | 0x002297fffe005279 |            1.1.0 | 002297005279
