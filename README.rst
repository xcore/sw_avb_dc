AVB-DC Software Stack
.....................

:Latest release: 1.0.0beta0
:Maintainer: ajwlucas
:Description: AVB-DC specific application software


Key Features
============

* Up to 4in/4out I2S audio channels
* Single stream support only
* 48 kHz sample rate only
* Support for 2 daisy-chained boards to a third Talker/Listener
* 1722 Talker and Listener (simultaneous) support
* 1722 MAAP support for Talkers
* 802.1Q MRP, MMRP, MVRP, SRP protocols
* gPTP server and protocol
* Media clock recovery and interface to PLL clock source
* Support for 1722.1 AVDECC: ADP, AECP (AEM) and ACMP

Firmware Overview
=================

This firmware is a daisy-chain endpoint implementation of Audio Video Bridging protocols for XMOS XS1-L16A-128-QF124-C10 devices.
It includes a PTP time server to provide a stable wallclock reference and clock recovery to synchronise listener audio to talker audio
codecs. The Stream Reservation Protocol is used to reserve bandwidth through 802.1 network infrastructure.

Known Issues
============

* Building will generate invalid warning messages that can be ignored:
    * *WARNING: Include file .build/generated/module_avb_1722_1/aem_descriptors.h missing*
    * *audio_i2s.h:187: warning: cannot unroll loop due to unknown loop iteration count*
* XTA will report a timing failure for route(1).
* Apple Macs may send bad PTP Sync timestamps under load. A workaround has been implemented in AVB-DC firmware to prevent loss of audio 
  which may may cause interoperability issues with non-compliant AVB bridges. This workaround can be disabled at the following
  line in module_gptp/src/gptp_config.h:
  *#define PTP_THROW_AWAY_SYNC_OUTLIERS 0*
* OS X device aggregation occasionally zeros incorrect streams when one device is disconnected from the aggregate of multi-output device.
* PTP Announce messages may have an incorrect Path Trace TLV with nodes appearing twice in the trace.
* SRP interoperability issues have been observed with Broadcom Hawkeye 53324 bridge reference designs running firmware v6.0.0.0. This
  may result in stream reservations not succeeding. 

Support
=======

The HEAD of this repository is a work in progress. It may or may not compile from time to time, and modules, code and features may be incomplete. For a stable, supported release please see the reference designs section at www.xmos.com.

Required software (dependencies)
================================

  * sc_avb (https://github.com/xcore/sc_avb.git)
  * sc_ethernet (https://github.com/xcore/sc_ethernet.git)
  * sc_i2c (https://github.com/xcore/sc_i2c.git)
  * sc_slicekit_support (https://github.com/xcore/sc_slicekit_support.git)
  * sc_otp (https://github.com/xcore/sc_otp.git)
  * sc_util (git@github.com:xcore/sc_util)

