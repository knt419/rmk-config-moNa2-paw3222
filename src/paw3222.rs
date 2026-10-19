//! PAW3222 trackball support for RMK 0.9.
//!
//! [`Paw3222`] is the register-level driver, a port of the ZMK driver this
//! board actually runs (`sekigon-gonnoc/zmk-driver-paw3222`, itself derived from
//! Zephyr's `input_paw32xx.c`): same product-ID probe, same reset sequence,
//! same `WRITE_PROTECT` unlock, same `DELTA_X`/`DELTA_Y` burst with 8-bit signed
//! deltas.
//!
//! It implements [`PointingDriver`], so RMK's own `PointingDevice` +
//! `PointingProcessor` drive it: accumulation, init retries, poll/report pacing
//! and mouse-button-carrying HID reports all come from RMK. `src/central.rs`
//! wires those two together because the generated entry point has to be
//! overridden to reach `&keymap` (see `README.md`).

use core::convert::Infallible;

use defmt::{error, info, warn};
use embassy_nrf::gpio::{Flex, Level, OutputDrive, Pull};
use embassy_time::{Duration, Timer};
use embedded_hal::digital::{ErrorType, InputPin, OutputPin};
use embedded_hal_async::spi::SpiBus;
use rmk::driver::flex_pin::FlexPin;
use rmk::input_device::pointing::{MotionData, PointingDriver, PointingDriverError};

// ---------------------------------------------------------------------------
// Registers (PAW3222 datasheet / Zephyr input_paw32xx.c)
// ---------------------------------------------------------------------------

const PRODUCT_ID1: u8 = 0x00;
const MOTION: u8 = 0x02;
const DELTA_X: u8 = 0x03;
const DELTA_Y: u8 = 0x04;
const OPERATION_MODE: u8 = 0x05;
const CONFIGURATION: u8 = 0x06;
const WRITE_PROTECT: u8 = 0x09;
const CPI_X: u8 = 0x0d;
const CPI_Y: u8 = 0x0e;
const DELTA_XY_HI: u8 = 0x12;

const PRODUCT_ID_PAW3222: u8 = 0x30;
const SPI_WRITE: u8 = 1 << 7;

const MOTION_STATUS_MOTION: u8 = 1 << 7;
const OPERATION_MODE_SLP_ENH: u8 = 1 << 4;
const OPERATION_MODE_SLP2_ENH: u8 = 1 << 3;
const OPERATION_MODE_SLP_MASK: u8 = OPERATION_MODE_SLP_ENH | OPERATION_MODE_SLP2_ENH;
const CONFIGURATION_RESET: u8 = 1 << 7;
const WRITE_PROTECT_ENABLE: u8 = 0x00;
const WRITE_PROTECT_DISABLE: u8 = 0x5a;

const RES_STEP: u16 = 38;
const RES_MIN: u16 = 16 * RES_STEP;
const RES_MAX: u16 = 127 * RES_STEP;

const RESET_DELAY_MS: u64 = 2;
const PRODUCT_ID_RETRIES: u8 = 10;
const PRODUCT_ID_RETRY_MS: u64 = 100;

/// Sensor resolution. 2280 = 60 counts/inch (must be a multiple of `RES_STEP`,
/// range 608..=4826). Lower CPI means fewer HID reports per inch of ball
/// travel, which is what keeps a BLE link from saturating.
pub const DEFAULT_CPI: u16 = 2280;

/// The sensor inverts both axes on this board (matching the ZMK overlay's
/// `invert-x; invert-y;`).
const INVERT_X: bool = true;
const INVERT_Y: bool = true;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Paw3222Error {
    Spi,
    InvalidProductId(u8),
    InvalidResolution(u16),
}

/// Register-level PAW3222 driver over a 3-wire (bidirectional SDIO) SPI bus.
pub struct Paw3222<SPI, CS, MOTION>
where
    SPI: SpiBus,
    CS: OutputPin,
    MOTION: InputPin,
{
    spi: SPI,
    cs: CS,
    motion: MOTION,
    resolution_cpi: u16,
}

impl<SPI, CS, MOTION> Paw3222<SPI, CS, MOTION>
where
    SPI: SpiBus,
    CS: OutputPin,
    MOTION: InputPin,
{
    pub fn new(spi: SPI, mut cs: CS, motion: MOTION, resolution_cpi: u16) -> Self {
        let _ = cs.set_high();
        Self {
            spi,
            cs,
            motion,
            resolution_cpi,
        }
    }

    /// MOTION is active low on this board.
    fn motion_pin_active(&mut self) -> bool {
        self.motion.is_low().unwrap_or(false)
    }

    /// Full bring-up: probe the product ID, reset, set CPI, arm sleep mode and
    /// drop any stale motion data.
    pub async fn init_sensor(&mut self) -> Result<(), Paw3222Error> {
        let mut last_id = 0u8;

        for attempt in 0..PRODUCT_ID_RETRIES {
            match self.read_reg(PRODUCT_ID1).await {
                Ok(id) if id == PRODUCT_ID_PAW3222 => {
                    info!("PAW3222 detected (product id {=u8:#04x})", id);
                    break;
                }
                Ok(id) => {
                    last_id = id;
                    warn!(
                        "PAW3222 unexpected product id {=u8:#04x} (attempt {=u8})",
                        id,
                        attempt + 1
                    );
                }
                Err(_) => {
                    warn!("PAW3222 product id read failed (attempt {=u8})", attempt + 1);
                }
            }

            if attempt + 1 == PRODUCT_ID_RETRIES {
                return Err(Paw3222Error::InvalidProductId(last_id));
            }
            Timer::after(Duration::from_millis(PRODUCT_ID_RETRY_MS)).await;
        }

        self.update_reg(CONFIGURATION, CONFIGURATION_RESET, CONFIGURATION_RESET)
            .await?;
        Timer::after(Duration::from_millis(RESET_DELAY_MS)).await;

        self.apply_resolution(self.resolution_cpi).await?;
        // Match the ZMK board config: no `force-awake`, so the sensor sleeps
        // between motions.
        self.set_force_awake(false).await?;

        // Clear residual motion state after the reset.
        let _ = self.read_reg(MOTION).await?;
        let _ = self.read_reg(DELTA_X).await?;
        let _ = self.read_reg(DELTA_Y).await?;
        let _ = self.read_reg(DELTA_XY_HI).await?;

        Ok(())
    }

    /// Read the motion register and, if the sensor has data, the X/Y deltas.
    /// Axis inversion (`INVERT_X`/`INVERT_Y`) is applied here, mirroring the
    /// ZMK overlay's `invert-x;` / `invert-y;` properties.
    pub async fn read_delta(&mut self) -> Result<Option<MotionData>, Paw3222Error> {
        let motion = self.read_reg(MOTION).await?;

        if motion & MOTION_STATUS_MOTION == 0 && !self.motion_pin_active() {
            return Ok(None);
        }

        let (mut dx, mut dy) = self.read_xy().await?;
        if INVERT_X {
            dx = -dx;
        }
        if INVERT_Y {
            dy = -dy;
        }

        Ok(Some(MotionData { dx, dy }))
    }

    /// One CS assertion, two register reads: `DELTA_X` then `DELTA_Y`.
    async fn read_xy(&mut self) -> Result<(i16, i16), Paw3222Error> {
        self.cs.set_low().map_err(|_| Paw3222Error::Spi)?;

        let result = async {
            let mut x = [0u8; 1];
            let mut y = [0u8; 1];

            self.spi
                .write(&[DELTA_X & 0x7f])
                .await
                .map_err(|_| Paw3222Error::Spi)?;
            self.spi.read(&mut x).await.map_err(|_| Paw3222Error::Spi)?;

            self.spi
                .write(&[DELTA_Y & 0x7f])
                .await
                .map_err(|_| Paw3222Error::Spi)?;
            self.spi.read(&mut y).await.map_err(|_| Paw3222Error::Spi)?;

            Ok((x[0] as i8 as i16, y[0] as i8 as i16))
        }
        .await;

        let _ = self.cs.set_high();
        result
    }

    pub async fn apply_resolution(&mut self, cpi: u16) -> Result<(), Paw3222Error> {
        if !(RES_MIN..=RES_MAX).contains(&cpi) {
            error!("PAW3222 CPI {=u16} out of range ({=u16}..={=u16})", cpi, RES_MIN, RES_MAX);
            return Err(Paw3222Error::InvalidResolution(cpi));
        }

        let value = (cpi / RES_STEP) as u8;

        self.write_reg(WRITE_PROTECT, WRITE_PROTECT_DISABLE).await?;
        self.write_reg(CPI_X, value).await?;
        self.write_reg(CPI_Y, value).await?;
        self.write_reg(WRITE_PROTECT, WRITE_PROTECT_ENABLE).await?;

        self.resolution_cpi = cpi;
        info!("PAW3222 CPI set to {=u16} ({=u8} x 38)", cpi, value);
        Ok(())
    }

    async fn set_force_awake(&mut self, enable: bool) -> Result<(), Paw3222Error> {
        let value = if enable { 0 } else { OPERATION_MODE_SLP_MASK };

        self.write_reg(WRITE_PROTECT, WRITE_PROTECT_DISABLE).await?;
        self.update_reg(OPERATION_MODE, OPERATION_MODE_SLP_MASK, value)
            .await?;
        self.write_reg(WRITE_PROTECT, WRITE_PROTECT_ENABLE).await?;

        Ok(())
    }

    async fn read_reg(&mut self, address: u8) -> Result<u8, Paw3222Error> {
        self.cs.set_low().map_err(|_| Paw3222Error::Spi)?;

        let result = async {
            self.spi
                .write(&[address & 0x7f])
                .await
                .map_err(|_| Paw3222Error::Spi)?;
            let mut value = [0u8; 1];
            self.spi
                .read(&mut value)
                .await
                .map_err(|_| Paw3222Error::Spi)?;
            Ok(value[0])
        }
        .await;

        let _ = self.cs.set_high();
        result
    }

    async fn write_reg(&mut self, address: u8, value: u8) -> Result<(), Paw3222Error> {
        self.cs.set_low().map_err(|_| Paw3222Error::Spi)?;

        let result = self
            .spi
            .write(&[address | SPI_WRITE, value])
            .await
            .map_err(|_| Paw3222Error::Spi);

        let _ = self.cs.set_high();
        result
    }

    async fn update_reg(&mut self, address: u8, mask: u8, value: u8) -> Result<(), Paw3222Error> {
        let current = self.read_reg(address).await?;
        self.write_reg(address, (current & !mask) | (value & mask))
            .await
    }
}

/// SDIO line for the sensor's 3-wire SPI.
///
/// RMK ships `FlexPin for embassy_nrf::gpio::Flex`, but it switches the line to
/// input with an internal pull-down. On this board the sensor drives SDIO
/// push-pull, so the pull-down only fights it during turnaround; the line is
/// left floating here instead.
pub struct SdioPin<'d>(Flex<'d>);

impl<'d> SdioPin<'d> {
    pub fn new(flex: Flex<'d>) -> Self {
        Self(flex)
    }
}

impl FlexPin for SdioPin<'_> {
    fn set_as_input(&mut self) {
        self.0.set_as_input(Pull::None);
    }

    fn set_as_output(&mut self) {
        self.0.set_level(Level::High);
        self.0.set_as_output(OutputDrive::Standard);
    }
}

impl ErrorType for SdioPin<'_> {
    type Error = Infallible;
}

impl OutputPin for SdioPin<'_> {
    fn set_low(&mut self) -> Result<(), Self::Error> {
        self.0.set_low();
        Ok(())
    }

    fn set_high(&mut self) -> Result<(), Self::Error> {
        self.0.set_high();
        Ok(())
    }
}

impl InputPin for SdioPin<'_> {
    fn is_high(&mut self) -> Result<bool, Self::Error> {
        Ok(self.0.is_high())
    }

    fn is_low(&mut self) -> Result<bool, Self::Error> {
        Ok(self.0.is_low())
    }
}

/// Plug PAW3222 into RMK's generic pointing pipeline: `PointingDevice` handles
/// accumulation, init retries and poll/report pacing, `PointingProcessor`
/// turns motion into HID reports (and keeps mouse-button state intact).
impl<SPI, CS, MOTION> PointingDriver for Paw3222<SPI, CS, MOTION>
where
    SPI: SpiBus,
    CS: OutputPin,
    MOTION: InputPin + embedded_hal_async::digital::Wait,
{
    type MOTION = MOTION;

    async fn init(&mut self) -> Result<(), PointingDriverError> {
        self.init_sensor().await.map_err(|e| match e {
            Paw3222Error::Spi => PointingDriverError::Spi,
            Paw3222Error::InvalidProductId(id) => PointingDriverError::InvalidProductId(id),
            Paw3222Error::InvalidResolution(_) => PointingDriverError::InvalidCpi,
        })
    }

    async fn read_motion(&mut self) -> Result<MotionData, PointingDriverError> {
        match self.read_delta().await {
            Ok(Some(motion)) => Ok(motion),
            Ok(None) => Ok(MotionData { dx: 0, dy: 0 }),
            Err(_) => Err(PointingDriverError::Spi),
        }
    }

    fn motion_pending(&mut self) -> bool {
        self.motion_pin_active()
    }

    fn motion_gpio(&mut self) -> Option<&mut Self::MOTION> {
        Some(&mut self.motion)
    }

    async fn set_resolution(&mut self, cpi: u16) -> Result<(), PointingDriverError> {
        self.apply_resolution(cpi)
            .await
            .map_err(|_| PointingDriverError::InvalidCpi)
    }
}
