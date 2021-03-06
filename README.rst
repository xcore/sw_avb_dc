AVB-DC Software Stack
.....................

:Latest release: 1.0.6rc0
:Maintainer: ajwlucas
:Description: AVB-DC specific application software


Key Features
============

* Up to 4in/4out I2S audio channels
* Support for 4 daisy-chained nodes
* 1722 Talker and Listener (simultaneous) support
* 1722 MAAP support for Talkers
* 802.1Q MRP, MVRP, SRP protocols
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
    * *xta: warning: target (0x0) of: (xscope_constructor+88) 0x18244 bl (lu10) -0xc124 not found in executable sections*
* Apple Macs may send bad PTP Sync timestamps under load. A workaround has been implemented in AVB-DC firmware to prevent loss of audio 
  which may may cause interoperability issues with non-compliant AVB bridges. This workaround can be disabled at the following
  line in module_gptp/src/gptp_config.h:
  *#define PTP_THROW_AWAY_SYNC_OUTLIERS 0*

Support
=======

The HEAD of this repository is a work in progress. It may or may not compile from time to time, and modules, code and features may be incomplete. For a stable, supported release please see the reference designs section at www.xmos.com.

Required software (dependencies)
================================

  * sc_avb (https://github.com/xcore/sc_avb.git)
  * sc_ethernet (https://github.com/xcore/sc_ethernet.git)
  * sc_i2c (https://github.com/xcore/sc_i2c.git)
  * sc_slicekit_support (git@github.com:xcore/sc_slicekit_support)
  * sc_otp (https://github.com/xcore/sc_otp.git)
  * sc_util (git://github.com/xcore/sc_util)

