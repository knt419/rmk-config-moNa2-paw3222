#![no_main]
#![no_std]

// The left half is a plain split peripheral: its matrix, EC11 encoder and
// battery level all come from keyboard.toml (`[split.peripheral]`), so there is
// nothing to add here.

use rmk::macros::rmk_peripheral;

#[rmk_peripheral(id = 0)]
mod keyboard_peripheral {}
