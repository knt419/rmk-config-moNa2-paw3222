use std::env;
use std::fs::File;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use const_gen::*;
use xz2::read::XzEncoder;

fn main() {
    // Vial needs its keyboard definition baked into the firmware.
    println!("cargo:rerun-if-changed=vial.json");
    generate_vial_config();

    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    File::create(out.join("memory.x"))
        .unwrap()
        .write_all(include_bytes!("memory.x"))
        .unwrap();

    println!("cargo:rerun-if-changed=keyboard.toml");
    println!("cargo:rerun-if-changed=memory.x");
    println!("cargo:rustc-link-search={}", out.display());
    println!("cargo:rustc-link-arg=--nmagic");
    println!("cargo:rustc-link-arg=-Tlink.x");
    println!("cargo:rustc-link-arg=-Tdefmt.x");
}

/// Emit `config_generated.rs` with the xz-compressed `vial.json` blob and the
/// 8-byte Vial keyboard id, which `#[rmk_central]` includes when
/// `host.vial_enabled = true`.
fn generate_vial_config() {
    let out_file = Path::new(&env::var_os("OUT_DIR").unwrap()).join("config_generated.rs");

    let mut content = String::new();
    File::open("vial.json")
        .expect("vial.json is missing: run `python3 tools/gen_vial_json.py`, or set [host].vial_enabled = false")
        .read_to_string(&mut content)
        .expect("cannot read vial.json");

    let vial_cfg = json::stringify(json::parse(&content).expect("vial.json is not valid JSON"));

    let mut keyboard_def_compressed: Vec<u8> = Vec::new();
    XzEncoder::new(vial_cfg.as_bytes(), 6)
        .read_to_end(&mut keyboard_def_compressed)
        .expect("failed to compress vial.json");

    let keyboard_id: Vec<u8> = vec![0xB9, 0xBC, 0x09, 0xB2, 0x9D, 0x37, 0x4C, 0xEA];
    let const_declarations = [
        const_declaration!(pub VIAL_KEYBOARD_DEF = keyboard_def_compressed),
        const_declaration!(pub VIAL_KEYBOARD_ID = keyboard_id),
    ]
    .map(|s| "#[allow(clippy::redundant_static_lifetimes)]\n".to_owned() + s.as_str())
    .join("\n");

    std::fs::write(out_file, const_declarations).expect("failed to write config_generated.rs");
}

