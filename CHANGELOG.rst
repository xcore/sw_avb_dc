sw_avb_dc Change Log
====================

1.0.4
-----
  * Bug fix to CONFIGURATION descriptor descriptor_counts_count field which was 1 small

  * Changes to dependencies:

    - sc_avb: 6.0.3beta0 -> 6.0.5beta0

      + Bug fix to prevent compile error when Talker is disabled
      + Update to 1722 MAAP to fix non-compliance issue on conflict check
      + Updates design guide documentation to include AVB-DC details
      + SPI task updated to take a structure with ports
      + Bug fix on cd length of acquire command response
      + Added EFU mode and address access flags to ADP capabilities

1.0.3
-----
  * Changes to dependencies:

    - sc_i2c: 2.2.0rc0 -> 2.4.0beta1

      + i2c_shared functions now take i2cPorts structure as param (rather than externed). This allows for
      + module_i2c_simple can now be built with support to send repeated starts and retry reads and writes NACKd by slave
      + module_i2c_shared added to allow multiple logical cores to safely share a single I2C bus
      + Removed readreg() function from single_port module since it was not safe
      + Documentation fixes

    - sc_avb: 6.0.2alpha0 -> 6.0.3beta0

      + Firmware upgrade functionality changed to support START_OPERATION commands to erase the flash
      + Several SRP bug fixes that would cause long connect/disconnection sequences to fail

    - sc_slicekit_support: 1.0.3rc0 -> 1.0.4rc0

      + Fix to the metainfo.

1.0.2
-----
  * Interim release for production manufacture

1.0.1
-----
  * Fixed erroneous number of stream formats in stream descriptors

  * Changes to dependencies:

    - sc_avb: 6.0.0alpha3 -> 6.0.1alpha0

      + VLAN ID is now reported via 1722.1 ACMP
      + Fixed XC pointer issue for v13.0.1 tools

1.0.0
-----
  * First release of daisy chain AVB
