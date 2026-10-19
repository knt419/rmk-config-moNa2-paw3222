MEMORY
{
  /* nRF52840 behind the Seeed/Adafruit UF2 bootloader on the XIAO nRF52840.
   * The bootloader owns 0x00000000..0x00026000 (see Zephyr's
   * nordic/nrf52840_partition_uf2_sdv7.dtsi, which the xiao_ble board uses), so
   * the application image must start at 0x26000 -- a 0x1000 origin would make
   * the flashed image overlap the bootloader.
   * No SoftDevice blob is linked: RMK uses the Nordic SoftDevice Controller
   * (nrf-sdc) compiled into the application. */
  FLASH : ORIGIN = 0x00026000, LENGTH = 872K
  RAM   : ORIGIN = 0x20000000, LENGTH = 256K
}
