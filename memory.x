MEMORY
{
  /* nRF52840 behind the UF2 bootloader on the XIAO nRF52840, **without** a
   * SoftDevice: protected MBR at 0x00000000..0x00001000, application at 0x1000.
   *
   * Do not "fix" this to 0x26000. That origin belongs to the SoftDevice
   * partition table (Zephyr's nordic/nrf52840_partition_uf2_sdv7.dtsi, which ZMK
   * uses), where the SoftDevice occupies 0x1000..0x26000. RMK links the Nordic
   * SoftDevice Controller (nrf-sdc) into the application, so there is no
   * SoftDevice blob and the app starts right after the MBR. A 0x26000 image
   * flashes "successfully" and then never boots: the bootloader jumps to 0x1000
   * and finds nothing.
   *
   * These values match the working moNa2 RMK config (razilyis/rmk-config-moNa2).
   */
  FLASH : ORIGIN = 0x00001000, LENGTH = 1020K
  RAM   : ORIGIN = 0x20000008, LENGTH = 255K
}
