#![no_main]
#![no_std]

mod paw3222;

use rmk::macros::rmk_central;

use rmk::event::{
    publish_event, EventSubscriber, LayerChangeEvent, PointingProcessorEvent, SubscribableEvent,
};
use rmk::input_device::pointing::{CursorConfig, PointingMode, ScrollConfig, SniperConfig};

/// Pointing device id of the trackball (must match the `PointingProcessor`).
const TRACKBALL_ID: u8 = 0;

/// Layer whose ball motion scrolls instead of moving the cursor.
/// ZMK config: layer 2 is SCROLL (`scroller { layers = <2>; }`).
const SCROLL_LAYER: u8 = 2;

/// Precision layer. ZMK config: layer 3 is SNIPE (`sniper { layers = <3>; }`).
const SNIPE_LAYER: Option<u8> = Some(3);

/// Counts of ball travel per scroll notch (144 ~= the moNa2 ZMK tuning).
const SCROLL_DIVISOR: u8 = 144;

/// Translate layer changes into pointing-mode changes.
///
/// RMK's `PointingProcessor` switches between cursor / scroll / sniper / caret
/// modes when it receives a `PointingProcessorEvent`, but nothing in RMK 0.9
/// publishes those from layer state, so this task bridges the two: it publishes
/// the mode that matches the layer the keymap just activated.
async fn pointing_mode_task() {
    let mut layer_events = LayerChangeEvent::subscriber();
    let mut current_layer: Option<u8> = None;

    loop {
        let event = layer_events.next_event().await;
        let layer: u8 = *event;

        if current_layer == Some(layer) {
            continue;
        }
        current_layer = Some(layer);

        let mode = if layer == SCROLL_LAYER {
            PointingMode::Scroll(ScrollConfig {
                multiplier_x: 1,
                divisor_x: SCROLL_DIVISOR,
                multiplier_y: 1,
                divisor_y: SCROLL_DIVISOR,
                invert_x: false,
                invert_y: false,
            })
        } else if SNIPE_LAYER == Some(layer) {
            PointingMode::Sniper(SniperConfig::default())
        } else {
            PointingMode::Cursor(CursorConfig::default())
        };

        defmt::info!("trackball mode -> layer {=u8}", layer);
        publish_event(PointingProcessorEvent {
            device_id: TRACKBALL_ID,
            mode,
        });
    }
}

#[rmk_central]
mod keyboard_central {
    /// Replace the generated "start everything" block so the PAW3222 can be
    /// built next to `&keymap`.
    ///
    /// `#[Overwritten(entry)]` only replaces the statements at the end of
    /// `main()`: chip/USB/BLE init, `rmk_config`, `storage`, `keymap`, `matrix`,
    /// `keyboard`, `host_service`, the battery ADC device and its processor are
    /// all still created by the macro and are in scope here. Everything the
    /// generated block used to spawn has to be spawned here instead —
    /// transports, input devices and processors included.
    #[Overwritten(entry)]
    fn rmk_entry() {
        use embassy_nrf::gpio::{Flex, Input, Level, Output, OutputDrive, Pull};
        use embassy_time::{Duration, Instant};
        use rmk::core_traits::Runnable;
        use rmk::driver::bitbang_spi::BitBangSpiBus;
        use rmk::input_device::pointing::{
            InitState, PointingDevice, PointingProcessor, PointingProcessorConfig,
        };
        use rmk::split::PeripheralMatrixConfig;

        // --- PAW3222 trackball (right / central half) -----------------------
        // SCLK   = D5  (P0.05)
        // SDIO   = D4  (P0.04, bidirectional 3-wire)
        // CS     = P0.09
        // MOTION = D0  (P0.02, active low)
        let sck = Output::new(p.P0_05, Level::High, OutputDrive::Standard);
        let sdio = crate::paw3222::SdioPin::new(Flex::new(p.P0_04));
        let cs = Output::new(p.P0_09, Level::High, OutputDrive::Standard);
        let motion = Input::new(p.P0_02, Pull::Up);
        let spi = BitBangSpiBus::new(sck, sdio);

        let sensor = crate::paw3222::Paw3222::new(spi, cs, motion, crate::paw3222::DEFAULT_CPI);

        let mut trackball = PointingDevice {
            sensor,
            init_state: InitState::Pending,
            poll_interval: Duration::from_millis(1),
            id: crate::TRACKBALL_ID,
            report_interval: Duration::from_millis(8),
            last_poll: Instant::MIN,
            last_report: Instant::MIN,
            accumulated_x: 0,
            accumulated_y: 0,
        };

        let mut pointing_processor = PointingProcessor::new(
            &keymap,
            PointingProcessorConfig {
                device_id: crate::TRACKBALL_ID,
                ..Default::default()
            },
        );

        // Auto mouse layer: `[[behavior.auto_mouse_layer]]` in keyboard.toml.
        let mut auto_mouse_layer = ::rmk::AutoMouseLayerRunner::new(&keymap);

        // --- transports -----------------------------------------------------
        let mut usb_transport = ::rmk::usb::UsbTransport::new(driver, rmk_config.device_config)
            .with_host_service(&host_service);
        let mut ble_transport = ::rmk::ble::BleTransport::new(
            ble_controller,
            ble_addr,
            rmk_config,
            [PeripheralMatrixConfig {
                rows: 4,
                cols: 6,
                row_offset: 0,
                col_offset: 0,
            }],
        )
        .with_host_service(&host_service);

        // --- run ------------------------------------------------------------
        ::rmk::embassy_futures::join::join(
            ::rmk::embassy_futures::join::join(
                ::rmk::run_all!(matrix, storage, adc_device, battery_processor, auto_mouse_layer),
                ::rmk::run_all!(trackball, pointing_processor),
            ),
            ::rmk::embassy_futures::join::join(
                ::rmk::embassy_futures::join::join(keyboard.run(), crate::pointing_mode_task()),
                ::rmk::embassy_futures::join::join(usb_transport.run(), ble_transport.run()),
            ),
        )
        .await;
    }
}
